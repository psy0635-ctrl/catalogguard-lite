import importlib
import sys

import pytest
import streamlit as st


@pytest.fixture()
def app_module(monkeypatch):
    sys.modules.pop("app", None)
    monkeypatch.setattr(st, "stop", lambda: None)
    return importlib.import_module("app")


def test_build_file_hash_returns_same_hash_for_same_bytes(app_module):
    first_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")
    second_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")

    assert first_hash == second_hash


def test_build_file_hash_returns_different_hash_for_different_bytes(app_module):
    first_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")
    second_hash = app_module.build_file_hash(b"product_id,price\nP002,2000\n")

    assert first_hash != second_hash


def test_mark_inspection_saved_stores_run_id_for_file_hash(app_module):
    session_state = {}
    file_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")

    app_module.mark_inspection_saved(
        session_state,
        file_hash=file_hash,
        inspection_run_id=42,
    )

    assert app_module.get_saved_inspection_run_id(session_state, file_hash) == 42


def test_saved_run_id_does_not_apply_to_new_file_hash(app_module):
    session_state = {}
    first_hash = app_module.build_file_hash(b"product_id,price\nP001,1000\n")
    second_hash = app_module.build_file_hash(b"product_id,price\nP002,2000\n")
    app_module.mark_inspection_saved(
        session_state,
        file_hash=first_hash,
        inspection_run_id=42,
    )

    assert app_module.get_saved_inspection_run_id(session_state, second_hash) is None
