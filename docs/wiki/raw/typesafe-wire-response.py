"""Ergonomic answer objects and response metadata, built on the generated wire schemas.

The wire structs in `typesafe_sdk._schemas.models` mirror the OpenAPI schema. The public answer types
subclass them, adding immutability and integer-keyed score maps, and let msgspec decode straight into
the public types — no wrapping layer. Because the wire answer structs are tagged, the public `Answer`
union decodes in one call; per-answer dispatch is kept only to skip answer kinds a future API adds.
"""

from functools import cached_property
from typing import Any, TypeAlias

import httpx2
import msgspec
from msgspec import field
from typing_extensions import Self, override

from typesafe_sdk._core.logging import logger
from typesafe_sdk._core.schemas.base import Response, field_path, validation_error
from typesafe_sdk._schemas import models as wire
from typesafe_sdk._schemas.models import ModelMetadata


# The generated wire fields are mutable; the public answer overrides intentionally make them read-only.
class NoulAnswer(wire.NoulAnswer, frozen=True, kw_only=True):
    """A yes/no answer.

    See the [noul primitive](https://docs.typesafe.ai/primitives/noul) for details.
    """

    noul: float  # pyrefly: ignore[bad-override]
    """Probability of a yes answer, from zero to one."""


class ChoiceAnswer(wire.ChoiceAnswer, frozen=True, kw_only=True):
    """A selected label and its probabilities.

    See the [choice primitive](https://docs.typesafe.ai/primitives/choice) for details.
    """

    choice: str  # pyrefly: ignore[bad-override]
    """The selected label."""
    confidence: float  # pyrefly: ignore[bad-override]
    """Reported confidence in the selected label."""
    probabilities: dict[str, float]  # pyrefly: ignore[bad-override]
    """Probabilities keyed by label."""


class ScoreAnswer(wire.ScoreAnswer, frozen=True, kw_only=True):
    """An expected score with its rubric and probabilities.

    See the [score primitive](https://docs.typesafe.ai/primitives/score) for details.
    """

    score: float  # pyrefly: ignore[bad-override]
    """Expected score, which may fall between the integer rubric levels."""
    confidence: float  # pyrefly: ignore[bad-override]
    """Reported confidence in the score."""
    # JSON object keys are strings; `dict[int, ...]` tells msgspec to coerce them to the integer score
    # levels at decode time. `Any` (not the recursive `JSONValue`) keeps the nested values decodable.
    legend: dict[int, str | dict[str, Any] | list[Any]]  # pyrefly: ignore[bad-override]
    """Rubric descriptions keyed by integer score."""
    probabilities: dict[int, float]  # pyrefly: ignore[bad-override]
    """Probabilities keyed by integer score."""


Answer: TypeAlias = NoulAnswer | ChoiceAnswer | ScoreAnswer
"""An answer to a single question, identified by its `type`."""


# The OpenAPI Usage schema still requires billing_units, which the API does not return.
class Usage(msgspec.Struct, kw_only=True):
    """Token counts for a request, when reported by the API."""

    input_tokens: int | None = None
    """Number of input tokens used, or `None` when the API did not report it."""
    output_tokens: int | None = None
    """Number of output tokens used, or `None` when the API did not report it."""


class _AnswerTag(msgspec.Struct):
    """Reads only an answer's discriminator so it can be routed to the right struct."""

    type: str


class _SystemOneBody(msgspec.Struct, kw_only=True):
    """Fast-path decode target: the whole tagged response, straight into the public types."""

    model: str
    usage: Usage
    answers: dict[str, Answer]


class _SystemOneRawBody(msgspec.Struct, kw_only=True):
    """Dispatch decode target; answers stay raw so unknown tags can be skipped one by one."""

    model: str
    usage: Usage
    answers: dict[str, msgspec.Raw]


_ANSWER_TYPES: dict[str, type[Answer]] = {
    "noul": NoulAnswer,
    "choice": ChoiceAnswer,
    "score": ScoreAnswer,
}

# One-shot decoder for the whole tagged response. The `Answer` structs carry a `tag_field`, so the
# public union decodes in a single call; per-answer dispatch (below) handles only forward-compat
# unknown types and precise error paths.
_RESPONSE_DECODER = msgspec.json.Decoder(_SystemOneBody)


class SystemOneResponse(Response, frozen=True, kw_only=True):
    """Answers grouped by question type with model and usage metadata.

    See [System One](https://docs.typesafe.ai/concepts/system-one) for details.
    """

    model: str
    """The model used to answer the request."""
    usage: Usage
    """Token usage for the request."""
    answers: dict[str, Answer] = field(default_factory=dict)
    """All answer objects keyed by question name."""

    @classmethod
    @override
    def _decode(cls, response: httpx2.Response) -> Self:
        native = cls._decode_native(response)
        return native if native is not None else cls._decode_by_dispatch(response)

    @classmethod
    def _decode_native(cls, response: httpx2.Response) -> Self | None:
        """Fast path: decode the whole tagged response in one msgspec call.

        Returns `None` — deferring to per-answer dispatch — when an answer type is unknown or a field
        is malformed. Dispatch then skips unknown types (the common forward-compat case) or re-raises
        with a precise field path.
        """
        try:
            body = _RESPONSE_DECODER.decode(response.content)
        except msgspec.ValidationError:
            return None
        return cls(model=body.model, usage=body.usage, answers=body.answers)

    @classmethod
    def _decode_by_dispatch(cls, response: httpx2.Response) -> Self:
        body = msgspec.json.decode(response.content, type=_SystemOneRawBody)
        answers: dict[str, Answer] = {}
        for name, raw in body.answers.items():
            try:
                tag = msgspec.json.decode(raw, type=_AnswerTag).type
            except msgspec.ValidationError as error:
                raise validation_error(response, f"answers.{name}.type") from error
            answer_type = _ANSWER_TYPES.get(tag)
            if answer_type is None:
                # Forward-compat: ignore answer types this SDK version does not model. The raw payload
                # is still available through `response.raw_http_response`.
                logger.warning("Ignoring answer %r with unrecognized type %r", name, tag)
                continue
            try:
                answers[name] = msgspec.json.decode(raw, type=answer_type)
            except msgspec.ValidationError as error:
                raise validation_error(response, field_path(("answers", name), error)) from error
        return cls(model=body.model, usage=body.usage, answers=answers)

    @cached_property
    def nouls(self) -> dict[str, NoulAnswer]:
        """Yes/no answers keyed by question name."""
        return {name: answer for name, answer in self.answers.items() if isinstance(answer, NoulAnswer)}

    @cached_property
    def choices(self) -> dict[str, ChoiceAnswer]:
        """Choice answers keyed by question name."""
        return {name: answer for name, answer in self.answers.items() if isinstance(answer, ChoiceAnswer)}

    @cached_property
    def scores(self) -> dict[str, ScoreAnswer]:
        """Score answers keyed by question name."""
        return {name: answer for name, answer in self.answers.items() if isinstance(answer, ScoreAnswer)}


class ListModelsResponse(Response, frozen=True, kw_only=True):
    """The models available to the account."""

    models: tuple[ModelMetadata, ...]
    """The available models."""

    @classmethod
    @override
    def _decode(cls, response: httpx2.Response) -> Self:
        body = msgspec.json.decode(response.content, type=wire.ModelMetadataList)
        return cls(models=tuple(body.models))
