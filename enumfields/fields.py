from django.core import checks
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
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


class EnumFieldMixin:

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


class EnumField(EnumFieldMixin, models.CharField):
    def __init__(self, enum, **kwargs):
        kwargs.setdefault("max_length", 10)
        super().__init__(enum, **kwargs)
        self.validators = []

    def check(self, **kwargs):
        return [
            *super().check(**kwargs),
            *self._check_max_length_fit(**kwargs),
        ]

    def _check_max_length_fit(self, **kwargs):
        if isinstance(self.max_length, int):
            unfit_values = [e for e in self.enum if len(str(e.value)) > self.max_length]
            if unfit_values:
                fit_max_length = max([len(str(e.value)) for e in self.enum])
                message = (
                    "Values {unfit_values} of {enum} won't fit in "
                    "the backing CharField (max_length={max_length})."
                ).format(
                    unfit_values=unfit_values,
                    enum=self.enum,
                    max_length=self.max_length,
                )
                hint = "Setting max_length={fit_max_length} will resolve this.".format(
                    fit_max_length=fit_max_length,
                )
                return [
                    checks.Warning(message, hint=hint, obj=self, id="enumfields.max_length_fit"),
                ]
        return []


class EnumIntegerField(EnumFieldMixin, models.IntegerField):
    @cached_property
    def validators(self):
        # Skip IntegerField validators, since they will fail with
        #   TypeError: unorderable types: TheEnum() < int()
        # when used database reports min_value or max_value from
        # connection.ops.integer_field_range method.
        next = super(models.IntegerField, self)
        return next.validators
