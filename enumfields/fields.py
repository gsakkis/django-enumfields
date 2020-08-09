from functools import partial

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

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


class EnumField(models.Field):

    default_error_messages = {
        'invalid': _('“%(value)s” is not a valid value for %(enum)s.'),
    }
    description = _("Enumeration for %(enum)s")

    descriptor_class = CastOnAssignDescriptor

    def __init__(self, enum, internal_class=models.CharField, **options):
        if isinstance(enum, str):
            enum = import_string(enum)

        if options.get("choices") is None:
            options["choices"] = [(i, getattr(i, 'label', i.name)) for i in enum]
        if options.get("max_length") is None:
            options["max_length"] = max(len(str(m.value)) for m in enum)

        self.enum = enum
        self.internal_class = internal_class
        self.internal_type = internal_class(**options).get_internal_type()
        self.empty_strings_allowed = internal_class.empty_strings_allowed
        super().__init__(**options)

    def check(self, **kwargs):
        # The base Field.check() calls _check_choices, which checks if 'max_length' is too small
        # to fit the longest choice. However this works only if the choice values are strings,
        # not enum members. So create a new temporary (shallow) copy of this field, change its
        # choices to enum values and check that instead.
        other = self.__copy__()
        other.choices = other.get_choices()
        errors = super(EnumField, other).check(**kwargs)
        # point the errors back to self
        for error in errors:
            error.obj = self
        return errors

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
                self.error_messages['invalid'],
                code='invalid',
                params={'value': value, 'enum': self.enum},
            )

    def get_internal_type(self):
        return self.internal_type

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
        kwargs.update(enum=self.enum, internal_class=self.internal_class)
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


EnumIntegerField = partial(EnumField, internal_class=models.IntegerField)
