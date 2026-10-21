"""Focused V7.3 RED UI/SQL integration checks without Streamlit dependencies."""
from __future__ import annotations
import ast
import sqlite3
from datetime import date
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent.parent
APP=HERE/'app.py'
CHART=HERE/'onboarding_red_chart.py'
SOURCE=APP.read_text(encoding='utf-8')
CHART_SOURCE=CHART.read_text(encoding='utf-8')
AST=ast.parse(SOURCE)
FUN={node.name:node for node in AST.body if isinstance(node,ast.FunctionDef)}
CODE=compile(ast.Module(body=[FUN['hyperverge_red_direct_payload']],type_ignores=[]),str(APP),'exec')
namespace={}
exec(CODE,namespace)
resolve=namespace['hyperverge_red_direct_payload']

class REDV73Tests(unittest.TestCase):
    def setUp(self):
        self.dfrom=date(2026,10,1)
        self.dto=date(2026,10,8)
        self.rows=[
            {'site':'NCR Bamnoli DC','site_key':'ncr bamnoli dc','count':1,'color':'#FCA5A5'},
            {'site':'Mysore XD','site_key':'mysore xd','count':1,'color':'#FCA5A5'},
        ]
    def test_click_resolves_exact_site_and_filters(self):
        self.assertEqual(resolve('ncr bamnoli dc',self.rows,self.dfrom,self.dto), {
            'kind':'hyperverge','site':'NCR Bamnoli DC','site_key':'ncr bamnoli dc',
            'count':1,'from':self.dfrom,'to':self.dto,
        })
    def test_same_site_repeat_has_no_guard(self):
        p1=resolve('ncr bamnoli dc',self.rows,self.dfrom,self.dto)
        p2=resolve('ncr bamnoli dc',self.rows,self.dfrom,self.dto)
        self.assertEqual(p1,p2)
        self.assertIsNot(p1,p2)
    def test_another_site(self):
        self.assertEqual(resolve('mysore xd',self.rows,self.dfrom,self.dto)['site'],'Mysore XD')
    def test_unknown_site_rejected(self):
        self.assertIsNone(resolve('unknown',self.rows,self.dfrom,self.dto))
        self.assertIsNone(resolve(None,self.rows,self.dfrom,self.dto))
    def test_dashboard_consumes_component_trigger(self):
        render=ast.get_source_segment(SOURCE,FUN['render_onboarding'])
        self.assertIn('render_hyperverge_red_chart(rows)',render)
        self.assertIn('hyperverge_red_direct_payload(',render)
        self.assertIn('st.session_state.pending_dialog = payload',render)
        self.assertNotIn('on_select="rerun"',render)
        self.assertNotIn('queue_hyperverge_red_selection(',render)
    def test_red_dialog_and_original_query_preserved(self):
        dialog=ast.get_source_segment(SOURCE,FUN['hyperverge_dialog'])
        self.assertIn('onboarding_red_for(DB_PATH, payload["from"], payload["to"], payload["site_key"])',dialog)
        self.assertIn('st.html(detail_frame_html(detail))', dialog)
        runner=ast.get_source_segment(SOURCE,FUN['render_dashboard'])
        self.assertIn('hyperverge_dialog(pending)',runner)
    def test_js_calls_direct_trigger_not_selection(self):
        self.assertIn("setTriggerValue('site_key', point.site_key)",CHART_SOURCE)
        self.assertIn("on_site_key_change=lambda: None",CHART_SOURCE)
        self.assertIn('key="main_hyperverge_red_direct_v3"',CHART_SOURCE)
        self.assertNotIn('on_select',CHART_SOURCE)
    def test_no_employee_data_in_chart(self):
        render=ast.get_source_segment(SOURCE,FUN['render_onboarding'])
        self.assertNotIn('"Employee ID"',render)
        self.assertNotIn('"Approved By"',render)
        self.assertNotIn('"employee_name"',render)
    def test_empty_red_card_preserved(self):
        render=ast.get_source_segment(SOURCE,FUN['render_onboarding'])
        self.assertIn('render_hyperverge_empty_state',render)
if __name__=='__main__':unittest.main()
