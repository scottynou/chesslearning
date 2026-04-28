from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


BEGINNER_SYSTEM_PROMPT = (
    "Tu es un coach d'échecs pour débutants. Tu expliques les coups avec des mots simples. "
    "Les meilleurs coups sont déjà fournis par Stockfish et par le système Elo-aware : tu ne dois pas inventer "
    "un autre meilleur coup. Ton travail est d'expliquer le coup sélectionné, son but, le plan associé, les "
    "réponses adverses probables et les erreurs à éviter. Tu dois toujours citer la pièce déplacée et les cases "
    "importantes. Tu ne dois jamais afficher de variante UCI brute comme g8f6 e2e3. Tu dois transformer les "
    "variantes en phrases compréhensibles. Tu dois éviter les phrases génériques. Si tu utilises un terme "
    "d'échecs, explique-le brièvement. Le modèle doit produire uniquement le JSON demandé. En mode débutant, "
    "écris 120 à 220 mots maximum, sans cp, sans jargon non expliqué, et sans phrase 'la variante moteur commence par'."
)

REVIEW_SYSTEM_PROMPT = (
    "Tu es un grand maitre pedagogique. Tu analyses le dernier coup adverse comme un joueur professionnel, "
    "mais tu l'expliques a un enfant debutant. Tu dois tenir compte de toute la partie, du plan choisi, "
    "du meilleur repere fourni par le moteur et de la qualite du coup. Tu produis un seul paragraphe clair, "
    "concret, sans jargon non explique, sans lignes UCI brutes, et sans inventer une autre evaluation."
)

LIVE_PLAN_SYSTEM_PROMPT = (
    "Tu es un coach d'echecs en direct. Les coups recommandes sont deja calcules par le moteur et les regles "
    "du produit : tu ne dois pas inventer un autre meilleur coup. Ton role est de resumer le plan vivant de la "
    "position en phrases courtes, concretes et utiles pour un debutant. Explique si le plan d'ouverture est "
    "encore jouable, termine ou abandonne, puis donne le prochain objectif strategique. Pas de variante UCI brute, "
    "pas de longue lecon."
)


EXPLAIN_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "moveLabel", "oneSentence", "sections", "technical", "translatedPv"],
    "properties": {
        "title": {"type": "string"},
        "moveLabel": {"type": "string"},
        "oneSentence": {"type": "string"},
        "sections": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "whatToDo",
                "mainIdea",
                "whyNow",
                "whatItProvokes",
                "nextPlan",
                "danger",
                "commonMistake",
                "betterThan",
            ],
            "properties": {
                "whatToDo": {"type": "string"},
                "mainIdea": {"type": "string"},
                "whyNow": {"type": "string"},
                "whatItProvokes": {"type": "string"},
                "nextPlan": {"type": "array", "items": {"type": "string"}},
                "danger": {"type": "string"},
                "commonMistake": {"type": "string"},
                "betterThan": {"type": "string"},
            },
        },
        "technical": {
            "type": "object",
            "additionalProperties": False,
            "required": ["san", "uci", "evalCp", "pv"],
            "properties": {
                "san": {"type": "string"},
                "uci": {"type": "string"},
                "evalCp": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "pv": {"type": "array", "items": {"type": "string"}},
            },
        },
        "translatedPv": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["moveNumber", "side", "beginnerLabel", "simpleExplanation"],
                "properties": {
                    "moveNumber": {"type": "integer"},
                    "side": {"type": "string"},
                    "beginnerLabel": {"type": "string"},
                    "simpleExplanation": {"type": "string"},
                },
            },
        },
    },
}

REVIEW_MOVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["coachNarrative"],
    "properties": {
        "coachNarrative": {
            "type": "string",
            "description": "Un seul paragraphe, 90 a 170 mots, technique mais comprehensible par un enfant debutant.",
        }
    },
}

LIVE_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "currentPlan", "whyChanged", "nextGoal", "event"],
    "properties": {
        "headline": {"type": "string"},
        "currentPlan": {"type": "string"},
        "whyChanged": {"type": "string"},
        "nextGoal": {"type": "string"},
        "event": {
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "severity", "title", "message"],
                    "properties": {
                        "id": {"type": "string"},
                        "severity": {"type": "string"},
                        "title": {"type": "string"},
                        "message": {"type": "string"},
                    },
                },
                {"type": "null"},
            ]
        },
    },
}


class AiProviderError(RuntimeError):
    pass


class AiProvider(ABC):
    @abstractmethod
    def explain_candidate(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        raise NotImplementedError

    def review_move(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        raise NotImplementedError

    def live_plan(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        raise NotImplementedError


def build_user_prompt(context: dict[str, Any]) -> str:
    return (
        "Produis uniquement un JSON conforme au schéma. "
        "Explique le coup sélectionné avec des phrases concrètes. "
        "N'affiche jamais les coups UCI bruts en mode débutant.\n\n"
        + json.dumps(context, ensure_ascii=False)
    )


def build_review_prompt(context: dict[str, Any]) -> str:
    return (
        "Produis uniquement un JSON conforme au schema. "
        "Le champ coachNarrative doit expliquer ce que l'adversaire a joue, si c'etait fort ou non, "
        "ce que cela change pour le plan du joueur, et quel meilleur repere l'adversaire pouvait choisir. "
        "Ne donne pas une liste; ecris un seul bloc lisible.\n\n"
        + json.dumps(context, ensure_ascii=False)
    )


def build_live_plan_prompt(context: dict[str, Any]) -> str:
    return (
        "Produis uniquement un JSON conforme au schema. "
        "Le champ headline doit tenir en quelques mots. currentPlan, whyChanged et nextGoal doivent faire une phrase courte chacun. "
        "Si aucun vrai changement ne merite notification, event vaut null.\n\n"
        + json.dumps(context, ensure_ascii=False)
    )
