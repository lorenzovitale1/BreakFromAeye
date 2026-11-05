from eyegaze.statemachine import GazeStateMachine
from eyegaze.states import GazeState, Obs

FPS = 15
DT = 1 / FPS


def make(**kw):
    p = dict(away_seconds=1.5, return_seconds=0.8, glitch_tolerance_seconds=0.25, cooldown_seconds=1.0,
             startup_warmup_seconds=3.0, uncertain_timeout_seconds=2.0)
    p.update(kw)
    return GazeStateMachine(**p)


def feed(sm, seq, t0=0.0):
    """seq: lista di (Obs, durata_s). Ritorna (transizioni, t finale)."""
    t, out = t0, []
    for obs, dur in seq:
        n = max(1, round(dur * FPS))
        for _ in range(n):
            tr = sm.update(t, obs)
            if tr:
                out.append(tr)
            t += DT
    return out, t


def warmed(sm, obs=Obs.AT):
    trs, t = feed(sm, [(obs, 3.5)])
    assert trs and trs[0].initial        # stato adottato senza comando
    return t


def test_no_command_during_warmup():
    sm = make()
    trs, _ = feed(sm, [(Obs.AWAY, 2.9)])
    assert trs == []                      # nessun comando nei primi 3 s, anche stando altrove


def test_startup_state_adopted_silently():
    sm = make()
    trs, _ = feed(sm, [(Obs.AWAY, 4.0)])
    assert len(trs) == 1 and trs[0].initial and trs[0].new_state == GazeState.LOOKING_AWAY


def test_steady_looking_at_screen_never_triggers():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.AT, 60)], t)
    assert trs == []


def test_away_triggers_exactly_once_after_threshold():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.AWAY, 10)], t)
    assert [x.new_state for x in trs] == [GazeState.LOOKING_AWAY]
    assert 1.4 <= trs[0].t - t <= 1.7


def test_away_shorter_than_threshold_does_nothing():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.AWAY, 1.2), (Obs.AT, 5)], t)
    assert trs == []


def test_blink_does_not_trigger_and_does_not_reset():
    sm = make()
    t = warmed(sm)
    # sguardo altrove con ammiccamento (NONE) a meta: il conteggio prosegue
    trs, _ = feed(sm, [(Obs.AWAY, 0.8), (Obs.NONE, 0.3), (Obs.AWAY, 1.0)], t)
    assert len(trs) == 1 and trs[0].new_state == GazeState.LOOKING_AWAY
    sm2 = make()
    t = warmed(sm2)
    trs, _ = feed(sm2, [(Obs.AT, 5), (Obs.NONE, 0.3), (Obs.AT, 5)], t)
    assert trs == []


def test_glitch_inside_away_run_is_tolerated():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.AWAY, 0.9), (Obs.AT, 0.1), (Obs.AWAY, 1.0)], t)
    assert len(trs) == 1


def test_return_triggers_after_08s_and_once():
    sm = make()
    t = warmed(sm)
    _, t = feed(sm, [(Obs.AWAY, 3)], t)
    trs, _ = feed(sm, [(Obs.AT, 10)], t)
    assert [x.new_state for x in trs] == [GazeState.LOOKING_AT_PC]
    assert 0.7 <= trs[0].t - t <= 1.1


def test_quick_glance_back_does_not_pause():
    sm = make(cooldown_seconds=0)
    t = warmed(sm)
    _, t = feed(sm, [(Obs.AWAY, 3)], t)
    trs, _ = feed(sm, [(Obs.AT, 0.4), (Obs.AWAY, 3)], t)
    assert trs == []


def test_cooldown_delays_flip_flop():
    sm = make(cooldown_seconds=5.0, away_seconds=0.5, return_seconds=0.5)
    t = warmed(sm)
    trs, t = feed(sm, [(Obs.AWAY, 1.0), (Obs.AT, 1.5)], t)
    assert [x.new_state for x in trs] == [GazeState.LOOKING_AWAY]     # il ritorno attende il cooldown
    trs, _ = feed(sm, [(Obs.AT, 6)], t)
    assert [x.new_state for x in trs] == [GazeState.LOOKING_AT_PC]


def test_camera_failure_sends_nothing_and_shows_unknown():
    sm = make()
    t = warmed(sm)
    trs, t = feed(sm, [(Obs.CAMERA_FAIL, 20)], t)
    assert trs == []
    assert sm.display_state == GazeState.UNKNOWN and not sm.camera_ok


def test_camera_fail_resets_pending_away_count():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.AWAY, 1.0), (Obs.CAMERA_FAIL, 0.5), (Obs.AWAY, 0.8)], t)
    assert trs == []                       # 1.0 + 0.8 non si sommano attraverso il guasto


def test_recovery_after_camera_failure_resumes_normally():
    sm = make()
    t = warmed(sm)
    _, t = feed(sm, [(Obs.CAMERA_FAIL, 5)], t)
    trs, _ = feed(sm, [(Obs.AWAY, 3)], t)
    assert len(trs) == 1 and trs[0].new_state == GazeState.LOOKING_AWAY


def test_prolonged_no_data_becomes_uncertain_without_commands():
    sm = make()
    t = warmed(sm)
    trs, _ = feed(sm, [(Obs.NONE, 6)], t)
    assert trs == [] and sm.display_state == GazeState.UNKNOWN


def test_uncertain_keeps_last_stable_state():
    sm = make()
    t = warmed(sm, Obs.AWAY)
    _, t = feed(sm, [(Obs.NONE, 6)], t)
    assert sm.stable_state == GazeState.LOOKING_AWAY


def test_progress_reports_target():
    sm = make()
    t = warmed(sm)
    _, t = feed(sm, [(Obs.AWAY, 0.75)], t)
    tgt, frac = sm.progress(t)
    assert tgt == GazeState.LOOKING_AWAY and 0.3 < frac < 0.7


def test_reset_requires_new_warmup():
    sm = make()
    t = warmed(sm)
    sm.reset()
    trs, _ = feed(sm, [(Obs.AWAY, 2.5)], t)
    assert trs == []
