from enumfields import EnumField
from django.db import models
from tests.enums import LabeledEnum


def test_shortness_check():
    class TestModel(models.Model):
        f1 = EnumField(LabeledEnum, max_length=-3, blank=True, null=True)
        f2 = EnumField(LabeledEnum, max_length=0, blank=True, null=True)
        f3 = EnumField(LabeledEnum, max_length=3, blank=True, null=True)

    errors = TestModel.check()
    assert len(errors) == 3
    assert errors[0].obj is TestModel.f1.field
    assert errors[1].obj is TestModel.f2.field
    assert errors[2].obj is TestModel.f3.field
    for error in errors:
        assert error.id == 'fields.E009'
        assert error.msg == "'max_length' is too small to fit the longest value in 'choices' (6 characters)."
