from enumfields.drf.fields import EnumField as EnumSerializerField
from enumfields.fields import BaseEnumField
from rest_framework.fields import ModelField


class EnumSupportSerializerMixin:
    enumfield_options = {}

    def build_standard_field(self, field_name, model_field):
        field_class, field_kwargs = (
            super().build_standard_field(field_name, model_field)
        )
        if isinstance(model_field, BaseEnumField):
            if issubclass(field_class, ModelField):
                del field_kwargs["model_field"]
            field_class = EnumSerializerField
            field_kwargs.update(enum=model_field.enum, **self.enumfield_options)

        return field_class, field_kwargs
