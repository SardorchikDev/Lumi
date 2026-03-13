"""Tests for src.utils.log — centralized logging."""

import logging
from unittest.mock import patch

from src.utils.log import get_logger


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_namespace(self):
        logger = get_logger("mymodule")
        assert logger.name == "lumi.mymodule"

    def test_src_prefix_normalized(self):
        logger = get_logger("src.utils.foo")
        assert logger.name == "lumi.utils.foo"

    def test_lumi_prefix_kept(self):
        logger = get_logger("lumi.core")
        assert logger.name == "lumi.core"

    def test_multiple_calls_same_logger(self):
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        assert logger1 is logger2
