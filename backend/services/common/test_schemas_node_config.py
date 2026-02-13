from pydantic import ValidationError
import pytest

from common.schemas import NodeConfigModel


def test_node_config_model_accepts_canonical_type():
    model = NodeConfigModel(node_id="nd-1", type="irrig")
    assert model.type == "irrig"


def test_node_config_model_normalizes_canonical_type_case():
    model = NodeConfigModel(node_id="nd-2", type="IRRIG")
    assert model.type == "irrig"


def test_node_config_model_rejects_legacy_alias_type():
    with pytest.raises(ValidationError):
        NodeConfigModel(node_id="nd-3", type="pump_node")
