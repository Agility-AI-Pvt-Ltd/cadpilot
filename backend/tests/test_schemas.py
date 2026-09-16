import pytest
from pydantic import ValidationError

from app.schemas import FixedInputs, Operation, OperationType


def test_dimensions_must_be_positive():
    with pytest.raises(ValidationError):
        FixedInputs(model_type="plant", length=0, width=1, height=1)


def test_box_requires_exact_dimensions():
    with pytest.raises(ValidationError):
        Operation(
            type=OperationType.CREATE_BOX, name="Envelope", dimensions={"length": 1, "width": 2}
        )
