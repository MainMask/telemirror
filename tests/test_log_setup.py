import logging

from telemirror.misc.log_setup import LOG_FORMAT, setup_stdout_logger


def test_returns_named_logger_with_one_handler():
    name = "telemirror.test.logsetup1"
    logger = setup_stdout_logger(name, "INFO")
    assert logger.name == name
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert logger.handlers[0].formatter._fmt == LOG_FORMAT


def test_idempotent():
    name = "telemirror.test.logsetup2"
    setup_stdout_logger(name, "INFO")
    setup_stdout_logger(name, "DEBUG")
    logger = logging.getLogger(name)
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG  # level still updated on the 2nd call
