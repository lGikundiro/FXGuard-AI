import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])


class FrontendStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.app_js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
        cls.styles_css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
        cls.accounts_js = (ROOT / "frontend" / "accounts.js").read_text(encoding="utf-8")
        parser = IdCollector()
        parser.feed(cls.html)
        cls.ids = parser.ids

    def test_html_ids_are_unique(self):
        duplicates = sorted({value for value in self.ids if self.ids.count(value) > 1})
        self.assertEqual(duplicates, [])

    def test_account_script_references_existing_elements(self):
        referenced_ids = set(re.findall(r"byId\('([^']+)'\)", self.accounts_js))
        missing = sorted(referenced_ids - set(self.ids))
        self.assertEqual(missing, [])

    def test_account_and_legal_surfaces_exist(self):
        required = {
            "signInButton",
            "resultSignUpButton",
            "authModal",
            "accountModal",
            "privacy",
            "terms",
            "acceptLegal",
            "deleteAccountButton",
        }
        self.assertEqual(sorted(required - set(self.ids)), [])

    def test_account_creation_is_offered_from_result_saving_only(self):
        topbar = self.html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
        save_prompt = self.html.split('id="saveAccountPrompt"', 1)[1].split(
            "<!-- Quiet export actions -->", 1
        )[0]
        self.assertNotIn("Create account", topbar)
        self.assertNotIn('id="signUpButton"', self.html)
        self.assertIn('id="resultSignUpButton"', save_prompt)
        self.assertIn("Save result", save_prompt)

    def test_export_bar_has_no_redundant_save_result_label(self):
        export_bar = self.html.split('id="exportBar"', 1)[1].split(
            '<div class="results-detail-grid">', 1
        )[0]
        self.assertNotIn("export-bar-left", export_bar)
        self.assertNotIn("<span>Save result</span>", export_bar)

    def test_main_app_loads_before_account_integration(self):
        self.assertLess(
            self.html.index("/static/app.js?v="),
            self.html.index("/static/accounts.js?v="),
        )

    def test_light_mode_controls_and_persistence_exist(self):
        self.assertIn("themeToggle", self.ids)
        self.assertIn('data-theme="light"', self.html)
        self.assertIn("fxguard_theme", self.html)
        self.assertIn("THEME_STORAGE_KEY", self.app_js)
        self.assertIn("applyTheme(", self.app_js)
        self.assertIn('[data-theme="light"]', self.styles_css)

    def test_signup_consent_checkbox_is_visible_and_validated(self):
        self.assertRegex(
            self.html,
            r'id="acceptLegal"\s+type="checkbox"\s+aria-describedby="authContactError"',
        )
        self.assertIn('.legal-acceptance input[type="checkbox"]', self.styles_css)
        self.assertIn("appearance: auto", self.styles_css)
        self.assertIn("classList.add('has-error')", self.accounts_js)
        self.assertIn("legalCheckbox?.focus()", self.accounts_js)

    def test_native_feedback_form_replaces_embedded_google_form(self):
        required = {
            "feedbackForm",
            "feedbackName",
            "feedbackCategory",
            "feedbackPhone",
            "feedbackComment",
            "feedbackSubmitButton",
            "feedbackStatus",
        }
        self.assertEqual(sorted(required - set(self.ids)), [])
        self.assertNotIn("<iframe", self.html)
        self.assertIn("`${API}/api/feedback`", self.app_js)
        self.assertIn("clarity_rating", self.app_js)
        self.assertIn("usefulness_rating", self.app_js)


if __name__ == "__main__":
    unittest.main()
