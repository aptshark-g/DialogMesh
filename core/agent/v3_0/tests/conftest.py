# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, ".")

import pytest


@pytest.fixture
def sample_input():
    return "scan memory at 0x004000"


@pytest.fixture
def technical_input():
    return "read the value at address 0x004010 and compare it with 0x004020"
