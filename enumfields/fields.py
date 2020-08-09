from django.core.exceptions import ValidationError
from django.db.models import Field
from django.utils.module_loading import import_string

from . import forms


class CastOnAssignDescriptor:
    """
    A property descriptor which ensures that `field.to_python()` is called on _every_ assignment to the field.

    This used to be provided by the `django.db.models.subclassing.Creator` class, which in turn
    was used by the deprecated-in-Django-1.10 `SubfieldBase` class, hence the reimplementation here.
    """

    def __init__(self, field):
        self.field = field

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return obj.__dict__[self.field.name]

    def __set__(self, obj, value):
        obj.__dict__[self.field.name] = self.field.to_python(value)


class BaseEnumField(Field):

    descriptor_class = CastOnAssignDescriptor

    def __init__(self, enum, **options):
        if isinstance(enum, str):
            enum = import_string(enum)
        self.enum = enum
        if "choices" not in options:
            options["choices"] = [(i, getattr(i, 'label', i.name)) for i in self.enum]
        super().__init__(**options)

    def to_python(self, value):
        if value is None or value == '':
            return None
        try:
            return self.enum(value)
        except ValueError:
            if isinstance(value, str):
                try:
                    return next(m for m in self.enum if str(m.value) == value or str(m) == value)
                except StopIteration:
                    pass
            raise ValidationError(
                '{} is not a valid value for enum {}'.format(value, self.enum),
                code="invalid_enum_value"
            )

    def get_prep_value(self, value):
        value = self.to_python(value)
        if value is not None:
            value = value.value
        return value

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return str(value.value) if value is not None else ''

    def get_default(self):
        default = super().get_default()
        if default is not None and self.has_default():
            default = self.enum(default)
        return default

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['enum'] = self.enum
        del kwargs['choices']
        return name, path, args, kwargs

    def get_choices(self, **kwargs):
        # Force enum fields' options to use the `value` of the enumeration
        # member as the `value` of SelectFields and similar.
        return [
            (i.value if isinstance(i, self.enum) else i, display)
            for (i, display)
            in super().get_choices(**kwargs)
        ]

    def formfield(self, form_class=None, choices_form_class=None, **kwargs):
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class or forms.EnumChoiceField,
            **kwargs
        )


class EnumField(BaseEnumField):

    def __init__(self, enum, **kwargs):
        super().__init__(enum, **kwargs)
        if self.max_length is None:
            self.max_length = max(len(str(m.value)) for m in self.enum)

    def check(self, **kwargs):
        # The base Field.check() calls _check_choices, which checks if 'max_length' is too small
        # to fit the longest choice. However this works only if the choice values are strings,
        # not enum members. So we create a new temporary (shallow) copy of this field, change its
        # choices to (string) enum values and check that instead.
        other = self.__copy__()
        other.choices = other.get_choices()
        errors = super(EnumField, other).check(**kwargs)
        # point the errors back to self
        for error in errors:
            error.obj = self
        return errors

    def get_internal_type(self):
        return "CharField"


class EnumIntegerField(BaseEnumField):

    def get_internal_type(self):
        return "IntegerField"
