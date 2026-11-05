"""Macchina a stati temporale: trasforma osservazioni per-frame in transizioni stabili.

Pura e deterministica: il tempo è passato dall'esterno (`t` in secondi), quindi si testa senza webcam né tablet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .states import GazeState, Obs


@dataclass(frozen=True)
class Transition:
    new_state: GazeState
    t: float
    initial: bool = False   # True = stato adottato dopo la stabilizzazione iniziale: NON genera comandi


class GazeStateMachine:
    def __init__(self, away_seconds: float = 1.5, return_seconds: float = 0.8,
                 glitch_tolerance_seconds: float = 0.25, cooldown_seconds: float = 1.0,
                 startup_warmup_seconds: float = 3.0, uncertain_timeout_seconds: float = 2.0):
        self.configure(away_seconds, return_seconds, glitch_tolerance_seconds, cooldown_seconds,
                       startup_warmup_seconds, uncertain_timeout_seconds)
        self.reset()

    def configure(self, away_seconds, return_seconds, glitch_tolerance_seconds, cooldown_seconds,
                  startup_warmup_seconds, uncertain_timeout_seconds) -> None:
        self.away_s = away_seconds
        self.return_s = return_seconds
        self.glitch_s = glitch_tolerance_seconds
        self.cooldown_s = cooldown_seconds
        self.warmup_s = startup_warmup_seconds
        self.uncertain_s = uncertain_timeout_seconds

    @classmethod
    def from_config(cls, cfg: dict) -> "GazeStateMachine":
        t = cfg["timing"]
        return cls(t["away_seconds"], t["return_seconds"], t["glitch_tolerance_seconds"],
                   t["cooldown_seconds"], t["startup_warmup_seconds"], t["uncertain_timeout_seconds"])

    def apply_config(self, cfg: dict) -> None:
        t = cfg["timing"]
        self.configure(t["away_seconds"], t["return_seconds"], t["glitch_tolerance_seconds"],
                       t["cooldown_seconds"], t["startup_warmup_seconds"], t["uncertain_timeout_seconds"])

    # ---- stato interno -------------------------------------------------
    def reset(self) -> None:
        """Riparte da capo (avvio o ricalibrazione): nuova stabilizzazione, nessun comando."""
        self._t0: Optional[float] = None
        self._stable: Optional[GazeState] = None
        self._cand: Optional[Obs] = None
        self._cand_since = 0.0
        self._opp_since: Optional[float] = None
        self._none_since: Optional[float] = None
        self._last_commit = -1e9
        self._camera_ok = True
        self._uncertain = False
        self._last_obs: Optional[Obs] = None

    @property
    def stable_state(self) -> Optional[GazeState]:
        return self._stable

    @property
    def camera_ok(self) -> bool:
        return self._camera_ok

    @property
    def display_state(self) -> GazeState:
        if self._stable is None or self._uncertain or not self._camera_ok:
            return GazeState.UNKNOWN
        return self._stable

    @property
    def warming_up(self) -> bool:
        return self._stable is None

    def progress(self, t: float) -> tuple[Optional[GazeState], float]:
        """(stato verso cui si sta andando, frazione 0..1 del tempo richiesto)."""
        if self._stable is None or self._cand is None:
            return None, 0.0
        target = _to_state(self._cand)
        if target == self._stable:
            return None, 0.0
        need = self.away_s if target == GazeState.LOOKING_AWAY else self.return_s
        return target, min(1.0, max(0.0, (t - self._cand_since) / need)) if need > 0 else 1.0

    # ---- aggiornamento -------------------------------------------------
    def update(self, t: float, obs: Obs) -> Optional[Transition]:
        if self._t0 is None:
            self._t0 = t

        if obs == Obs.CAMERA_FAIL:
            # nessuna prova: azzera i conteggi, conserva l'ultimo stato stabile, nessun comando
            self._camera_ok = False
            self._cand = None
            self._opp_since = None
            self._none_since = None
            return None
        self._camera_ok = True

        if obs == Obs.NONE:
            if self._none_since is None:
                self._none_since = t
            if t - self._none_since >= self.uncertain_s:
                self._uncertain = True
                self._cand = None
                self._opp_since = None
            return None
        self._none_since = None
        self._uncertain = False

        self._track_candidate(t, obs)

        # fase di stabilizzazione: adotta lo stato senza emettere comandi
        if self._stable is None:
            if t - self._t0 >= self.warmup_s and self._cand is not None:
                self._stable = _to_state(self._cand)
                return Transition(self._stable, t, initial=True)
            return None

        if self._cand is None:
            return None
        target = _to_state(self._cand)
        if target == self._stable:
            return None
        need = self.away_s if target == GazeState.LOOKING_AWAY else self.return_s
        if t - self._cand_since >= need and t - self._last_commit >= self.cooldown_s:
            self._stable = target
            self._last_commit = t
            return Transition(target, t)
        return None

    def _track_candidate(self, t: float, obs: Obs) -> None:
        if self._cand is None:
            self._cand, self._cand_since, self._opp_since = obs, t, None
            return
        if obs == self._cand:
            self._opp_since = None
            return
        # osservazione contraria al candidato: conta solo se dura più della tolleranza
        if self._opp_since is None:
            self._opp_since = t
        if t - self._opp_since >= self.glitch_s:
            self._cand, self._cand_since, self._opp_since = obs, self._opp_since, None


def _to_state(obs: Obs) -> GazeState:
    return GazeState.LOOKING_AT_PC if obs == Obs.AT else GazeState.LOOKING_AWAY
