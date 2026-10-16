"""Ağ gerektirmeyen testler: REST çağrılarının doğru yolu, parametreleri ve doğrulamalarını kontrol eder."""
import asyncio
import unittest

from micup import Bot, AuditAction
from micup.client import Bot as ClientBot
from micup.overwrites import merge_overwrites


class FakeBot(Bot):
    def __init__(self):
        super().__init__("123.secret")
        self.calls = []
        self.response = None

    async def _request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.response


def run(coro):
    return asyncio.run(coro)


class AuditReason(unittest.TestCase):
    def test_raw_value_no_encoding(self):
        b = FakeBot()
        self.assertEqual(b._audit("Türkçe neden ş/ğ %41"), {"extra_headers": {"X-Audit-Log-Reason": "Türkçe neden ş/ğ %41"}})

    def test_trimmed(self):
        b = FakeBot()
        self.assertEqual(b._audit("  spam  ")["extra_headers"]["X-Audit-Log-Reason"], "spam")

    def test_blank_and_too_long_ignored(self):
        b = FakeBot()
        self.assertEqual(b._audit("   "), {})
        self.assertEqual(b._audit(None), {})
        self.assertEqual(b._audit("a" * 513), {})

    def test_header_sent_on_pin(self):
        b = FakeBot()
        run(b.pin_message("c1", "m1", reason="test"))
        method, path, kw = b.calls[0]
        self.assertEqual((method, path), ("PUT", "/v1/channels/c1/pins/m1"))
        self.assertEqual(kw["extra_headers"], {"X-Audit-Log-Reason": "test"})


class Pins(unittest.TestCase):
    def test_list_pins_clamps_limit(self):
        b = FakeBot()
        run(b.list_pins("c1", limit=999))
        self.assertEqual(b.calls[0][2]["params"], {"limit": 50})


class Reactions(unittest.TestCase):
    def test_emoji_encoded(self):
        b = FakeBot()
        run(b.add_reaction("c1", "m1", "isim:123"))
        path = b.calls[0][1]
        self.assertIn("/reactions/isim%3A123/@me", path)


class AuditLogs(unittest.TestCase):
    def test_params(self):
        b = FakeBot()
        b.response = {"audit_log_entries": []}
        run(b.list_audit_logs("g1", limit=10, user_id="u1", action_type=AuditAction.MEMBER_BAN_ADD))
        method, path, kw = b.calls[0]
        self.assertEqual((method, path), ("GET", "/v1/guilds/g1/audit-logs"))
        self.assertEqual(kw["params"], {"limit": 10, "user_id": "u1", "action_type": 22})

    def test_before_and_after_rejected(self):
        b = FakeBot()
        with self.assertRaises(ValueError):
            run(b.list_audit_logs("g1", before="1", after="2"))

    def test_limit_out_of_range(self):
        b = FakeBot()
        with self.assertRaises(ValueError):
            run(b.list_audit_logs("g1", limit=101))
        self.assertEqual(b.calls, [])


class Moderation(unittest.TestCase):
    def test_timeout_requires_duration(self):
        b = FakeBot()
        with self.assertRaises(ValueError):
            run(b.timeout("g1", "u1"))

    def test_ban_path(self):
        b = FakeBot()
        run(b.ban("g1", "u1", reason="spam"))
        self.assertEqual((b.calls[0][0], b.calls[0][1]), ("PUT", "/v1/guilds/g1/bans/u1"))


class Slowmode(unittest.TestCase):
    def test_range(self):
        b = FakeBot()
        with self.assertRaises(ValueError):
            run(b.set_slowmode("c1", 21601))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ChannelPermissions(unittest.TestCase):
    _merge = staticmethod(merge_overwrites)

    def test_merge_replaces_only_target(self):
        existing = [
            {"id": "1", "type": 0, "allow": "1048576", "deny": "1024"},
            {"id": "2", "type": 1, "allow": "0", "deny": "2048"},
        ]
        out = self._merge(existing, "1", allow=1050624, deny=0)
        self.assertIn({"id": "2", "type": 1, "allow": "0", "deny": "2048"}, out)
        self.assertIn({"id": "1", "type": 0, "allow": "1050624", "deny": "0"}, out)
        self.assertEqual(len(out), 2)

    def test_merge_keeps_existing_type_and_adds_new(self):
        out = self._merge([{"id": "5", "type": 1, "allow": "0", "deny": "0"}], "5", deny=2048)
        self.assertEqual(out, [{"id": "5", "type": 1, "allow": "0", "deny": "2048"}])
        out = self._merge([], "9", allow=1048576)
        self.assertEqual(out, [{"id": "9", "type": 0, "allow": "1048576", "deny": "0"}])

    def test_merge_remove(self):
        existing = [{"id": "1", "type": 0, "allow": "1", "deny": "0"}, {"id": "2", "type": 0, "allow": "0", "deny": "2"}]
        self.assertEqual(self._merge(existing, "1", remove=True), [{"id": "2", "type": 0, "allow": "0", "deny": "2"}])

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            self._merge([], "1", allow=2048, deny=2048)

    def test_set_permission_sends_full_list(self):
        b = FakeBot()
        b.response = {"id": "c", "permission_overwrites": [
            {"id": "1", "type": 0, "allow": "0", "deny": "1024"},
            {"id": "2", "type": 0, "allow": "2048", "deny": "0"},
        ]}
        run(b.set_channel_permission("c", "1", allow=1048576))
        method, path, kwargs = b.calls[-1]
        self.assertEqual((method, path), ("PATCH", "/v1/channels/c"))
        self.assertEqual(kwargs["json"], {"permission_overwrites": [
            {"id": "2", "type": 0, "allow": "2048", "deny": "0"},
            {"id": "1", "type": 0, "allow": "1048576", "deny": "0"},
        ]})

    def test_clear_permission(self):
        b = FakeBot()
        b.response = {"id": "c", "permission_overwrites": [{"id": "1", "type": 0, "allow": "1", "deny": "0"}]}
        run(b.clear_channel_permission("c", "1"))
        self.assertEqual(b.calls[-1][2]["json"], {"permission_overwrites": []})
