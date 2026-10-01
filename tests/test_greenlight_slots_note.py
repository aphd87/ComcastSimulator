"""Acquire a Pitched Show intro ends with a reminder of how many new-show
slots are left this year (shared by acquire / build / AI-pitched shows)."""
import pytest
from streamlit.testing.v1 import AppTest


def _script(n_greenlit):
    import sys
    import streamlit as st
    sys.path.insert(0, ".")
    st.session_state.team_name = "T"
    st.session_state.active_network = "oxygen"
    st.session_state.year = 1
    st.session_state.greenlit_ids_this_year = set(range(n_greenlit))
    import app_pages.greenlight as greenlight
    greenlight.render()


@pytest.mark.parametrize("n, expected", [
    (0, "You have 3 of 3 new-show slots left this year"),
    (2, "You have 1 of 3 new-show slots left this year"),
    (3, "You've used all 3 new-show slots this year"),
])
def test_slot_reminder(n, expected):
    at = AppTest.from_function(_script, args=(n,), default_timeout=30)
    at.run()
    assert not at.exception, list(at.exception)
    assert expected in " ".join(m.value for m in at.markdown)
