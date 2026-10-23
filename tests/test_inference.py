import numpy as np

from screen_detector.inference.ort_backend import choose_provider
from screen_detector.inference.preprocess import FixedPreprocessor


def test_preprocessor_has_fixed_nchw_buffer():
    preprocessor = FixedPreprocessor(32)
    result = preprocessor(np.zeros((12, 20, 3), dtype=np.uint8))
    assert result.tensor.shape == (1, 3, 32, 32)
    assert result.tensor.dtype == np.float32
    assert result.source_width == 20 and result.source_height == 12


def test_directml_provider_is_available():
    assert choose_provider("directml") == "DmlExecutionProvider"
