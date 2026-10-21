"""Focused UI polish regression tests. No real employee data is used."""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from selectable_detail_table import detail_frame_html, selectable_detail_html

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)
FUNCTIONS = {
    node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)
}


def inline_js(filename: str) -> str:
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_JS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing _JS in {filename}")


NODE_SIMULATOR = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Node {
  constructor() { this.children=[];this.style={};this.textContent='';this.attributes={}; }
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.children.push(node);return node;}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(k,v){this.attributes[k]=String(v);}
  addEventListener(){}
}
const layer=new Node(),legend=new Node(),label=new Node();
const root={querySelector(query){return {
 '.bau-method-slices':layer,'.bau-method-legend':legend,
 '.bau-method-center-total':label
}[query];}};
const document={createElement(){return new Node();},createElementNS(){return new Node();}};
const render=(new Function('document', input.js.replace('export default function(component)',
  'return function(component)')))(document);
render({parentElement:{querySelector(){return root;}},data:input.data,setTriggerValue(){}});
process.stdout.write(JSON.stringify({
 percentages:legend.children.map(el=>el.children[2].textContent),
 total:label.textContent,arcs:layer.children.length
}));
"""


class OnboardingPercentJS(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute the inline donut JS")
    def test_positive_manual_never_coexists_with_false_100_percent_aadhaar(self):
        js = inline_js("onboarding_donut.py")
        for aadhar, manual, expected in [
            (994, 6, ["99.4%", "0.6%"]),
            (996, 4, ["99.6%", "0.4%"]),
            (9995, 5, ["99.95%", "0.05%"]),
            (500, 500, ["50.0%", "50.0%"]),
            (100, 0, ["100.0%", "0.0%"]),
        ]:
            with self.subTest(aadhar=aadhar, manual=manual):
                proc = subprocess.run(
                    ["node", "-e", NODE_SIMULATOR],
                    input=json.dumps({"js": js, "data": {"aadhar": aadhar, "manual": manual}}),
                    capture_output=True, text=True, timeout=15, check=True,
                )
                actual = json.loads(proc.stdout)
                self.assertEqual(actual["percentages"], expected)
                self.assertEqual(actual["arcs"], 1 if not (aadhar and manual) else 2)


class SelectableTableTests(unittest.TestCase):
    def test_id_is_plain_selectable_text_and_html_is_escaped(self):
        markup = selectable_detail_html(
            ["Employee ID", "Employee Name", "Aadhaar Number", "Working Hours"],
            [{"Employee ID": "000-A&B-07", "Employee Name": '<img src=x onerror=alert(1)>',
              "Aadhaar Number": "000012345678", "Working Hours": 7.75}],
        )
        self.assertIn('class="bau-copy-id"', markup)
        self.assertIn('user-select:all !important', markup)
        self.assertIn('000-A&amp;B-07', markup)
        self.assertIn('000012345678', markup)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', markup)
        self.assertNotIn('<img ', markup)
        self.assertNotIn('onclick', markup)
        self.assertNotIn('<script', markup)

    def test_frame_adapter_does_not_require_streamlit_dataframe(self):
        class FakeFrame:
            columns = ["Employee ID", "Phone Number"]
            def iter_rows(self, named=False):
                self_named = named
                if not self_named:
                    raise ValueError("must use named rows")
                return iter([{"Employee ID": "A-001", "Phone Number": "0987654321"}])
        html = detail_frame_html(FakeFrame())
        self.assertIn("A-001", html)
        self.assertIn("0987654321", html)
        for name in ["attendance_dialog", "hyperverge_dialog", "onboarding_method_dialog", "flex_dialog", "flex_working_dialog"]:
            self.assertIn('st.html(', ast.get_source_segment(APP, FUNCTIONS[name]), name)


class DateAndProgressTests(unittest.TestCase):
    def test_date_picker_defaults_to_latest_and_resets_stale_state(self):
        function = FUNCTIONS["select_report_day"]
        scope = {}
        fake_st = SimpleNamespace(
            session_state={},
            selectbox=lambda label, dates, format_func, key: fake_st.session_state[key],
        )
        # The AST helper compiles without importing the Streamlit app or database.
        mod = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        exec(compile(mod, "<date_picker>", "exec"), {
            "pl": SimpleNamespace(DataFrame=object), "st": fake_st,
            "fmt_date": lambda d: str(d),
        }, scope)
        picker = scope["select_report_day"]
        class Frame:
            def is_empty(self): return False
            def get_column(self, _name): return self
            def unique(self): return self
            def to_list(self): return [date(2026, 10, 4), date(2026, 10, 15)]
        self.assertEqual(picker(Frame(), "Flex Used date", "demo"), date(2026, 10, 15))
        fake_st.session_state["demo"] = date(2026, 10, 4)
        self.assertEqual(picker(Frame(), "Flex Used date", "demo"), date(2026, 10, 4))
        fake_st.session_state["demo"] = date(2026, 9, 1)
        self.assertEqual(picker(Frame(), "Flex Used date", "demo"), date(2026, 10, 15))

    def test_flex_site_scope_and_usage_day_picker_and_attendance_style_trend(self):
        source = ast.get_source_segment(APP, FUNCTIONS["render_flex"])
        self.assertIn('if not (regions or site_keys):', source)
        self.assertIn('render_flex_scope_prompt()', source)
        self.assertIn('select_report_day(usage, "Flex Used date", "flex_usage_single_day")', source)
        self.assertIn('usage.filter(pl.col("data_date") == usage_day)', source)
        self.assertIn('"from": usage_day, "to": usage_day', source)
        self.assertIn('flex_working_on_used_days(all_dates, flex_used)', source)
        self.assertIn('filtered("flex_usage", filters, ["Total Flex Used"])', source)
        self.assertIn('fig = px.line(', source)
        self.assertIn('clicked_date = coerce_date(p.get("x"))', source)
        self.assertIn('clicked_date.isoformat()', source)
        self.assertIn('sdf = chart_data.filter(', source)
        self.assertNotIn('render_flex_region_prompt', source)
        self.assertNotIn('"Show history through selected date"', source)
        self.assertNotIn('"Flex Working Hours date"', source)
        self.assertNotIn('px.scatter(', source)
        prompt = ast.get_source_segment(APP, FUNCTIONS['render_flex_scope_prompt'])
        self.assertIn('Please select a region or select facilities', prompt)

    def test_pages_keep_sites_accessible(self):
        fn = FUNCTIONS["page_site_rows"]
        ns = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), "<pages>", "exec"), ns)
        page = ns["page_site_rows"]
        rows = [{"site": f"Site {x:02}", "site_key": str(x)} for x in range(23)]
        self.assertEqual(len(page(rows, 0)[0]), 10)
        self.assertEqual((len(page(rows, 2)[0]), page(rows, 2)[1:]), (3, (2, 3)))
        self.assertEqual(page(rows, 100)[1], 2)

    def test_import_progress_caption_and_stages_are_wired(self):
        parser = (ROOT / "parsers.py").read_text(encoding="utf-8")
        settings_source = ast.get_source_segment(APP, FUNCTIONS["render_settings"])
        self.assertIn('progress: Callable[[float, str], None] | None = None', parser)
        self.assertIn('report_progress(0.28, f"Parsing', parser)
        self.assertIn('st.progress(0, text=', settings_source)
        self.assertIn('progress_caption.caption(', settings_source)
        self.assertIn('progress=parser_progress', settings_source)
        self.assertNotIn('Data available through', APP)

    def test_flex_svg_cannot_gain_dark_focus_border(self):
        source = (ROOT / "flex_usage_chart.py").read_text(encoding="utf-8")
        self.assertIn('stroke:none !important;stroke-width:0 !important', source)
        self.assertIn('.bau-flex-segment.clickable:focus-visible', source)
        self.assertIn("rect.addEventListener('keydown'", source)
        self.assertIn("rect.addEventListener('click'", source)
        self.assertNotIn('stroke:var(--st-text-color', source)


if __name__ == "__main__":
    unittest.main()
