"""Command dispatch with the safety checklist (the bouncer).

The router decides *whether* a command may run; it never does STT, TTS, or
intent recognition, and it never auto-confirms. Checklist, in order:

  1. registered intent?           -> unknown_intent
  2. session trust >= min_level?  -> auth_required (+ missing factors)
  3. confirmation satisfied?      -> confirmation_required
  4. run the developer's handler  -> ok (+ handler result)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..auth.levels import AuthEngine, AuthSession


@dataclass
class RouteResult:
    """Uniform return shape for every dispatch."""

    status: str                     # ok | unknown_intent | auth_required |
                                    # confirmation_required | handler_error
    intent: str
    required_level: Optional[str] = None
    current_level: Optional[str] = None
    missing_factors: List[str] = field(default_factory=list)
    confirmation_type: Optional[str] = None   # audio | explicit
    result: Any = None              # the handler's return value (status=ok)
    error: Optional[str] = None


class CommandRouter:
    def __init__(self, command_config: Dict[str, Any], engine: AuthEngine) -> None:
        self.engine = engine
        self._commands: Dict[str, Dict[str, Any]] = {
            c["intent"]: c for c in command_config.get("commands", [])
        }
        self._handlers: Dict[str, Callable[..., Any]] = {}

    def register(self, intent: str, handler: Callable[..., Any]) -> None:
        """Plug in your handler for an intent declared in commands.yaml."""
        if intent not in self._commands:
            raise KeyError(f"Intent '{intent}' is not declared in commands.yaml")
        self._handlers[intent] = handler

    def dispatch(
        self,
        intent: str,
        session: AuthSession,
        context: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
    ) -> RouteResult:
        """Run the checklist and, if everything passes, the handler.

        `confirmed=True` means the developer's UX already obtained the
        confirmation this command requires (the library never assumes it).
        """
        context = context or {}

        # 1. known intent?
        cmd = self._commands.get(intent)
        if cmd is None:
            return RouteResult(status="unknown_intent", intent=intent)

        # 2. enough trust?
        decision = self.engine.authorize(cmd["min_level"], session)
        if not decision.allowed:
            return RouteResult(
                status="auth_required",
                intent=intent,
                required_level=decision.required_level,
                current_level=decision.current_level,
                missing_factors=decision.missing_factors,
            )

        # 3. confirmation satisfied?
        confirmation = cmd.get("confirmation", "none")
        if confirmation != "none" and not confirmed:
            return RouteResult(
                status="confirmation_required",
                intent=intent,
                required_level=decision.required_level,
                current_level=decision.current_level,
                confirmation_type=confirmation,
            )

        # 4. run the developer's handler.
        handler = self._handlers.get(intent)
        if handler is None:
            return RouteResult(
                status="handler_error",
                intent=intent,
                error=f"No handler registered for '{intent}'",
            )
        try:
            result = handler(context)
        except Exception as exc:  # surface, don't swallow
            return RouteResult(status="handler_error", intent=intent, error=str(exc))
        return RouteResult(
            status="ok",
            intent=intent,
            current_level=decision.current_level,
            result=result,
        )
