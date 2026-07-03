"""Tests for AccountSwitcher.parse_accounts()."""
from account_switcher import AccountSwitcher


class StubConfig:
    """Minimal object exposing get_config(section, key, default)."""

    def __init__(self, accounts_value):
        self.accounts_value = accounts_value

    def get_config(self, section, key, default=None):
        if section == 'Accounts' and key == 'accounts':
            return self.accounts_value
        return default


def test_empty_string_gives_no_accounts():
    assert AccountSwitcher.parse_accounts(StubConfig('')) == []


def test_single_pair():
    accounts = AccountSwitcher.parse_accounts(StubConfig('user@example.com:secret'))
    assert accounts == [{'email': 'user@example.com', 'password': 'secret'}]


def test_multiple_pairs_with_whitespace():
    raw = '  a@x.dev : pw1 ,b@x.dev:pw2,   c@x.dev:pw3  '
    accounts = AccountSwitcher.parse_accounts(StubConfig(raw))
    assert accounts == [
        {'email': 'a@x.dev', 'password': 'pw1'},
        {'email': 'b@x.dev', 'password': 'pw2'},
        {'email': 'c@x.dev', 'password': 'pw3'},
    ]


def test_malformed_entry_without_colon_is_skipped():
    raw = 'a@x.dev:pw1, no-colon-here, b@x.dev:pw2'
    accounts = AccountSwitcher.parse_accounts(StubConfig(raw))
    assert accounts == [
        {'email': 'a@x.dev', 'password': 'pw1'},
        {'email': 'b@x.dev', 'password': 'pw2'},
    ]


def test_password_containing_colon_is_preserved():
    accounts = AccountSwitcher.parse_accounts(StubConfig('a@x.dev:pa:ss:word'))
    assert accounts == [{'email': 'a@x.dev', 'password': 'pa:ss:word'}]
