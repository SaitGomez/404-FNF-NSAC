"""Interface regression tests for FlameBench (commit 18).

Rewritten to use pytest with real assertions and repository-relative paths.
Printing information or taking a screenshot is not a test, so every check here
asserts something that would fail if the correction were reverted.

Requires Playwright with Chromium:
    python3 -m pip install --break-system-packages playwright
    python3 -m playwright install chromium
If a Chromium build is already present, point CHROME_PATH at it instead, e.g.
    CHROME_PATH=/usr/bin/google-chrome python3 -m pytest pipeline/test_app.py -q

The whole module is skipped when neither Playwright nor a browser is available,
so the data tests still run on a machine without a browser.
"""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")
sync_playwright = playwright_api.sync_playwright


def _browser_kwargs():
    """Use the browser Playwright installed, or an explicit CHROME_PATH."""
    exe = os.environ.get("CHROME_PATH")
    kwargs = {"args": ["--no-sandbox"]}
    if exe:
        if not Path(exe).exists():
            pytest.skip(f"CHROME_PATH={exe} does not exist")
        kwargs["executable_path"] = exe
    return kwargs


# A failed webfont request is an environment artifact, not an application fault.
IGNORED_CONSOLE = ("ERR_TUNNEL_CONNECTION_FAILED", "ERR_NAME_NOT_RESOLVED",
                   "ERR_INTERNET_DISCONNECTED", "ERR_PROXY_CONNECTION_FAILED",
                   "fonts.googleapis.com", "fonts.gstatic.com")


@pytest.fixture(scope="module")
def page():
    if not INDEX.exists():
        pytest.skip("index.html has not been built; run python3 src/build.py")
    errors = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(**_browser_kwargs())
        except Exception as exc:                       # no browser binary available
            pytest.skip(f"could not launch Chromium: {exc}")
        pg = browser.new_page(viewport={"width": 1500, "height": 950})
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(INDEX.as_uri())
        pg.wait_for_timeout(700)
        pg.errors = errors
        yield pg
        browser.close()


def real_errors(page):
    return [e for e in page.errors if not any(t in e for t in IGNORED_CONSOLE)]


def show(page, block_id, step, pillar=None):
    """Make a block active and open one of its steps.

    Setting `step` alone is not enough: the work area renders whichever block is
    active, so the block has to be selected too.
    """
    page.evaluate(
        """([id, step, pil]) => {
             const b = blk(id); if(!b) return;
             S.active = id; b.step = step;
             if(pil) b.st.pil = pil;
             renderAll();
           }""",
        [block_id, step, pillar])
    page.wait_for_timeout(400)


# ---------------------------------------------------------------- loading
def test_page_loads_without_javascript_errors(page):
    assert real_errors(page) == [], real_errors(page)


def test_interface_language_is_english(page):
    assert page.evaluate("document.documentElement.lang") == "en"


def test_no_spanish_text_in_the_rendered_interface(page):
    """The dashboard must present in English."""
    text = page.evaluate("document.body.innerText")
    spanish = ["Investigaciones", "Prevención", "Detección", "Supresión", "Cuaderno",
               "Guardar hallazgo", "Presión", "Combustible", "pruebas", "Fuera de rango",
               "Descargar", "Gravedad", "Espesor", "Diluyente"]
    found = [w for w in spanish if w in text]
    assert not found, f"Spanish text still rendered: {found}"


def test_example_project_has_three_linked_blocks(page):
    assert page.evaluate("S.blocks.map(b=>b.type).join(',')") == "C1,C2,C3"


# ---------------------------------------------------------------- commit 2 / 8
def test_individual_test_count_in_the_app(page):
    assert page.evaluate("T.filter(isIndividual).length") == 1871


def test_notes_and_visualizations_are_not_plot_eligible(page):
    assert page.evaluate("T.filter(t=>t.lvl!=='test').every(t=>!t.plot)") is True


def test_aggregates_are_excluded_from_plotted_points(page):
    assert page.evaluate("T.filter(t=>t.lvl==='test-day summary'||t.lvl==='campaign summary').every(t=>!t.plot)") is True


def test_per_variable_quality_does_not_void_whole_rows(page):
    """A flow warning must leave that row's oxygen usable."""
    assert page.evaluate("T.filter(t=>t.qa==='flow_invalid').some(t=>QV.o2(t))") is True


# ---------------------------------------------------------------- commit 5 / 6 / 7
def test_signed_flow_is_reachable_from_the_app(page):
    assert page.evaluate("T.filter(t=>t.flminr!=null&&t.flminr<0).length") == 4


def test_charted_flow_is_never_negative(page):
    assert page.evaluate("T.every(t=>t.flb==null||t.flb>=0)") is True


def test_initial_and_final_oxygen_are_distinct_fields(page):
    assert page.evaluate("T.some(t=>t.o2i!=null&&t.o2f!=null&&t.o2i!==t.o2f)") is True


def test_pressure_has_three_provenance_states(page):
    states = page.evaluate("[...new Set(T.map(t=>t.pstate))].sort()")
    assert states == ["assumed", "measured", "no_data"]


def test_a_row_without_pressure_is_not_reported_as_out_of_range(page):
    """Commit 7: missing data is reported as missing, not as a mismatch."""
    verdict = page.evaluate("""() => {
      const t = T.find(x => x.pstate === 'no_data');
      const v = rowVerdict(t, {o2:null, p:[50,60], fl:null});
      return {missing: v.missing, outside: v.outside};
    }""")
    assert verdict["missing"] == ["pressure"]
    assert verdict["outside"] == []


# ---------------------------------------------------------------- commit 4
def test_qualifier_parser_keeps_bounds_and_ranges(page):
    got = page.evaluate("""() => ({
      censored: parseCell('<0.1').kind,
      approx: parseCell('~ 21.5').kind,
      interval: parseCell('22.1 to 22.0').kind,
      intervalEnds: [parseCell('22.1 to 22.0').lower, parseCell('22.1 to 22.0').upper],
      exact: parseCell('21.5 %').kind,
      censoredExcluded: cellNum('<0.1'),
      negative: parseCell('-4 cm/s').value
    })""")
    assert got["censored"] == "censored"
    assert got["approx"] == "approximate"
    assert got["interval"] == "interval"
    assert got["intervalEnds"] == [22.0, 22.1]
    assert got["exact"] == "exact"
    assert got["censoredExcluded"] is None, "a bound must not be read as an exact number"
    assert got["negative"] == -4


# ---------------------------------------------------------------- commit 9
def test_flammability_map_has_no_universal_burn_zones(page):
    """Option B: the chart must not label regions as burning or extinguishing."""
    show(page, 'C', 1, 'prev')
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "reference for PMMA rods" in text
    assert "not a classifier" in text
    for banned in ("the material burns", "Above the curve"):
        assert banned not in text


def test_map_counts_unknown_outcomes_separately(page):
    show(page, 'C', 1, 'prev')
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "have no outcome recorded" in text


def test_tests_without_outcome_get_a_neutral_marker(page):
    style = page.evaluate("""() => {
      const t = T.find(x => x.plot && x.st==='solid' && !x.outr);
      return outcomeStyle(t);
    }""")
    assert style["shape"] == "diamond"
    assert "mute" in style["c"], "an unknown outcome must not be coloured as a result"


def test_one_g_check_is_not_presented_as_validating_the_exponent(page):
    show(page, 'C', 1)
    # Part of this explanation sits inside the advanced-assumptions disclosure,
    # so the rendered markup is what to inspect, not only the visible text.
    html = page.evaluate("document.querySelector('#work').innerHTML")
    assert "cannot validate" in html or "does not validate" in html
    visible = page.evaluate("document.querySelector('#work').innerText")
    for banned in ("validates the exponent", "confirms the exponent"):
        assert banned not in visible


# ---------------------------------------------------------------- commit 13
def test_suppression_figure_is_computed_not_hardcoded(page):
    """The data top out at 20.9 % O2, so the text must not claim 22 %."""
    show(page, 'C', 1, 'sup')
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "20.9" in text, "the computed maximum oxygen should appear"
    assert "up to 22 %" not in text


def test_partial_pressure_of_oxygen_is_shown(page):
    show(page, 'C', 2, 'prev')
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "partial pressure" in text.lower()


def test_compatibility_uses_four_states_not_a_binary(page):
    states = page.evaluate("Object.keys(CSTATE).sort()")
    assert states == ["match", "none", "partial", "related"]
    labels = page.evaluate("Object.values(CSTATE).map(x=>x[1])")
    assert "Insufficient evidence" in labels


# ---------------------------------------------------------------- commit 10
def test_axis_maximum_covers_the_data(page):
    """The old fixed limits of 330 kPa and 60 cm/s cut off valid points."""
    dmax = page.evaluate("DMAX")
    assert dmax["p"] >= 506.6, dmax
    assert dmax["fl"] >= 85.28, dmax


def test_chart_reports_points_outside_the_visible_range(page):
    dropped = page.evaluate("""() => {
      const o = {xr:[0,10], yr:[0,10], xl:'x', yl:'y', pts:[{x:5,y:5},{x:99,y:99},{x:-5,y:1}]};
      chart(o); return o.dropped;
    }""")
    assert dropped == 2, "chart must count points it does not draw"


# ---------------------------------------------------------------- commit 11
def test_scenario_warns_when_two_environments_are_identical(page):
    twins = page.evaluate("twinEnvs('lunar')")
    assert "Pressurised rover (Moon)" in twins


def test_derived_relevance_is_disclosed(page):
    assert page.evaluate("!!RELIX_DERIVED.earth") is True
    assert page.evaluate("!!RELIX_DERIVED.eva_prep") is True


def test_ranking_separates_evidence_from_relevance(page):
    show(page, 'A', 0)
    r = page.evaluate("""() => {
      const b = blk('A'), L = c1List(b);
      return L.slice(0,3).map(x => ({id:x.v.id, ev:x.evidenceScore, rel:x.missionScore}));
    }""")
    assert all("ev" in x and "rel" in x for x in r)
    assert any(abs(x["ev"] - x["rel"]) > 1 for x in r), "the two scores should not be the same number"


def test_forced_comparison_does_not_pool_data_for_modelling(page):
    pooled = page.evaluate("""() => {
      const b = blk('A');
      b.st.cmp = ['PSI-25','PSI-102'];        // solid tests vs smoke detection
      b.st.force = true;
      return {aff: cmpAffinity(b.st), poolable: cmpPoolable(b.st)};
    }""")
    assert pooled["aff"] < 0.30
    assert pooled["poolable"] is False, "a forced comparison must not license pooling"
    page.evaluate("() => { const b = blk('A'); b.st.cmp = ['PSI-25','PSI-99']; b.st.force = false; renderAll(); }")
    page.wait_for_timeout(200)


# ---------------------------------------------------------------- commit 12
def test_constant_variable_disables_the_model_with_an_explanation(page):
    err = page.evaluate("doFit('lin',[5,5,5,5],[1,2,3,4]).err")
    assert err and "does not vary" in err


def test_fit_and_validation_are_reported_separately(page):
    show(page, 'B', 2)
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "Fit on these data" in text
    assert "not a validation" in text
    assert "Out-of-sample validation" in text


def test_cross_validation_groups_rather_than_splitting_rows(page):
    res = page.evaluate("""() => {
      const P = [];
      for(let g=0; g<4; g++) for(let i=0; i<4; i++)
        P.push([g*10+i, 2*(g*10+i)+1, {invn:'INV'+g, tbl:'t', fuel:'f', dil:'', grav:'ug'}]);
      return cvGrouped('lin', P);
    }""")
    assert res["ok"] is True
    assert res["groups"] == 4, "folds must be built from independent groups"


def test_cross_validation_refuses_when_there_are_too_few_groups(page):
    res = page.evaluate("""() => {
      const P = [];
      for(let i=0; i<12; i++) P.push([i, 2*i, {invn:'ONE', tbl:'t', fuel:'f', dil:'', grav:'ug'}]);
      return cvGrouped('lin', P);
    }""")
    assert res["ok"] is False
    assert "group" in res["reason"]


def test_extrapolation_is_labelled_and_not_styled_as_interpolation(page):
    page.click('.cell[data-id="B"][data-step="2"]')
    page.wait_for_timeout(400)
    page.evaluate("() => { const b = blk('B'); b.st.xq = 999; b.st.xqAuto = false; renderWork(); }")
    page.wait_for_timeout(300)
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "Extrapolation" in text
    assert "not validated experimentally" in text


def test_residual_spread_is_not_called_a_prediction_interval(page):
    show(page, 'B', 2)
    text = page.evaluate("document.querySelector('#work').innerText")
    if "Residual spread" in text:
        assert "not a prediction interval" in text


def test_preconfigured_analysis_carries_its_justification(page):
    page.evaluate("() => { const b = blk('B'); b.link = null; b.st.invs = ['PSI-69']; b.st.cols = null; pickXY(b); b.step = 2; renderAll(); }")
    page.wait_for_timeout(500)
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "Preconfigured analysis" in text
    assert "not interchangeable" in text or "meaningful only within one fuel" in text


# ---------------------------------------------------------------- commit 15
def test_prediction_field_keeps_focus_while_typing(page):
    show(page, 'B', 2)
    page.click("#mq")
    page.evaluate("document.querySelector('#mq').value=''")
    for ch in "28.5":
        page.keyboard.type(ch)
        page.wait_for_timeout(40)
        assert page.evaluate("document.activeElement && document.activeElement.id") == "mq", \
            f"focus lost after typing {ch!r}"
    assert page.evaluate("document.querySelector('#mq').value") == "28.5"


def test_save_iteration_without_a_model_explains_itself(page):
    msg = page.evaluate("""() => {
      const b = blk('B'); b.st.last = null; b.step = 2;
      document.querySelectorAll('#canvasWrap .note').forEach(n=>n.remove());
      const btn = [...document.querySelectorAll('[data-act="hist"]')][0];
      if(!btn) return 'no-button';
      btn.disabled = false; btn.click();
      const n = document.querySelector('#canvasWrap .note');
      return n ? n.textContent : 'no-feedback';
    }""")
    assert msg not in ("no-feedback", "no-button"), "the button must act or explain why it cannot"
    assert "Nothing to save" in msg


def test_save_buttons_are_disabled_without_a_result(page):
    """Logistic regression on a continuous Y cannot fit, so there is nothing to save."""
    page.evaluate("""() => {
      const b = blk('B'); S.active = 'B'; b.step = 2; b.link = null;
      b.st.x = 'o2b'; b.st.y = 'p'; b.st.method = 'log'; b.st.preset = ''; b.st.last = null;
      renderAll();
    }""")
    page.wait_for_timeout(300)
    assert "needs a Y variable of 0 and 1" in page.evaluate("document.querySelector('#work').innerText")
    disabled = page.evaluate("""[...document.querySelectorAll('[data-act="hist"],[data-act="save"][data-what="model"]')].map(b=>b.disabled)""")
    assert disabled, "the save controls should be present"
    assert all(disabled), "save controls should be disabled when there is no result"
    page.evaluate("() => { const b = blk('B'); b.st.method = 'lin'; b.st.cols = null; pickXY(b); renderAll(); }")
    page.wait_for_timeout(200)


# ---------------------------------------------------------------- commit 14
def test_workspace_round_trips_through_serialisation(page):
    ok = page.evaluate("""() => {
      const before = S.blocks.length;
      const s = serializeState();
      if(!validState(s)) return 'invalid';
      applyState(JSON.parse(JSON.stringify(s)));
      return S.blocks.length === before ? 'ok' : 'lost-blocks';
    }""")
    assert ok == "ok"


def test_workspace_rejects_a_mismatched_version(page):
    assert page.evaluate("validState({v:999, blocks:[], nb:[]})") is False


def test_storage_failure_is_not_fatal(page):
    """Commit 14: a blocked storage API must not break the app."""
    res = page.evaluate("""() => {
      const real = window.localStorage;
      try{
        Object.defineProperty(window, 'localStorage', {get(){ throw new Error('blocked'); }, configurable:true});
        const r = saveWorkspace();
        return {ok: r.ok, msg: r.msg};
      } finally {
        Object.defineProperty(window, 'localStorage', {value: real, configurable:true, writable:true});
      }
    }""")
    assert res["ok"] is False
    assert res["msg"]


# ---------------------------------------------------------------- commit 16
def test_details_element_is_closed(page):
    show(page, 'A', 1)
    counts = page.evaluate("""() => {
      const h = document.querySelector('#work').innerHTML;
      return {open: (h.match(/<details/g)||[]).length, close: (h.match(/<\\/details>/g)||[]).length};
    }""")
    assert counts["open"] == counts["close"], counts


def test_legend_never_emits_an_undefined_background(page):
    html = page.evaluate("legend([{t:'external', h:1},{c:'var(--s1)', t:'normal'}])")
    assert "undefined" not in html


def test_outcomes_are_distinguished_by_shape_as_well_as_colour(page):
    shapes = page.evaluate("OUTLEG.map(x=>x.shape)")
    assert len(set(shapes)) == len(shapes), "each outcome needs its own shape"


def test_lunar_gravity_is_shown_with_enough_precision(page):
    show(page, 'C', 1)
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "0.165" in text, "lunar gravity should not be rounded to 0.17"


def test_keyboard_can_reach_the_step_cells(page):
    assert page.evaluate("""[...document.querySelectorAll('.cell')].every(c=>c.getAttribute('tabindex')==='0')""") is True


# ---------------------------------------------------------------- commit 17
def test_external_evidence_shows_status_and_check_date(page):
    show(page, 'C', 0)
    text = page.evaluate("document.querySelector('#work').innerText")
    assert "Status:" in text
    assert "checked" in text


def test_fm2_is_not_claimed_to_have_flown(page):
    status = page.evaluate("D.ext.find(x=>x.id==='fm2').status")
    assert "Planned" in status
    assert "Not flown" in status or "no results" in status


def test_assistant_abstains_when_nothing_is_retrieved(page):
    page.evaluate("ask('zzzqqq nonexistent topic xyzzy')")
    page.wait_for_timeout(500)
    text = page.evaluate("document.querySelector('#aiOut').innerText")
    assert "Not enough information" in text


def test_assistant_retrieves_relevant_sources_for_the_evaluation_set(page):
    """Each fixed evaluation question must return at least one source."""
    results = page.evaluate("AI_EVAL.map(q => ({q, n: retrieve(q, 6).length}))")
    empty = [r["q"] for r in results if r["n"] == 0]
    assert not empty, f"no sources retrieved for: {empty}"


def test_assistant_first_source_is_on_topic_for_a_dust_question(page):
    titles = page.evaluate("retrieve('What is lunar dust?', 4).map(d=>d.title)")
    assert any("DAFT" in t or "dust" in t.lower() for t in titles), titles


# ---------------------------------------------------------------- disclaimers
def test_app_states_it_does_not_certify_materials(page):
    text = page.evaluate("document.body.innerText")
    assert "does not certify materials" in text


# ---------------------------------------------------------------- layout
def test_no_horizontal_overflow_on_a_narrow_viewport(page):
    page.set_viewport_size({"width": 420, "height": 900})
    page.wait_for_timeout(400)
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
    page.set_viewport_size({"width": 1500, "height": 950})
    page.wait_for_timeout(200)
    assert overflow is False


def test_ranking_table_keeps_its_columns_at_1440px(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    show(page, 'A', 0)
    headers = page.evaluate("""[...document.querySelectorAll('#work table th')].map(t=>t.innerText.trim()).filter(Boolean)""")
    page.set_viewport_size({"width": 1500, "height": 950})
    assert "Compatibility" in headers
    assert any("Matching" in h for h in headers)


def test_still_no_javascript_errors_after_the_whole_walkthrough(page):
    assert real_errors(page) == [], real_errors(page)
