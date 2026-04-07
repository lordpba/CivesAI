"""
Servizio di calibrazione regionale NUTS-2.

Carica snapshot di calibrazione da disco quando disponibili e fornisce
un'interfaccia stabile per la GUI e per la preparazione delle simulazioni.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("mirofish.calibration")


class CalibrationService:
    """Fornisce dati di calibrazione regionale per la generazione dei profili."""

    _instance = None
    _profiles: Dict[str, Dict[str, Any]] = {}
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._load_data()

    def _load_data(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed"))
        profiles_path = os.path.join(base_dir, "calibration_profiles.json")

        self._profiles = self._build_default_profiles()

        if os.path.exists(profiles_path):
            try:
                with open(profiles_path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    self._profiles.update(loaded)
                logger.info(f"Caricati profili di calibrazione da disco: {profiles_path}")
            except Exception as exc:
                logger.warning(f"Impossibile caricare il file di calibrazione {profiles_path}: {exc}")
        else:
            logger.info("File di calibrazione non trovato su disco, uso il dataset base incorporato.")

        self._loaded = True

    def _build_default_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Dataset starter NUTS-2 per demo e sviluppo locale."""
        templates = self._zone_templates()
        region_specs = [
            ("ITC1", "Piemonte", "north", {"economic": {"gdp_per_capita": 36400, "employment_rate": 65.0, "median_income_eur": 33200, "wealth_index": 118}, "demographic": {"median_age": 46.0, "unemployment_rate": 6.0}, "social": {"institutional_trust": 5.6, "life_satisfaction_mean": 6.3}}),
            ("ITC2", "Valle d'Aosta", "north", {"economic": {"gdp_per_capita": 39200, "employment_rate": 67.8, "median_income_eur": 35400, "wealth_index": 127}, "demographic": {"internet_users_pct": 88.5, "education_tertiary_pct": 30.4}, "social": {"interpersonal_trust": 6.2, "institutional_trust": 5.8, "life_satisfaction_mean": 6.6}}),
            ("ITC3", "Liguria", "north", {"economic": {"gdp_per_capita": 35200, "employment_rate": 62.9, "median_income_eur": 32300, "wealth_index": 112}, "demographic": {"median_age": 48.1, "unemployment_rate": 6.9, "sport_participation_pct": 28.6}, "social": {"institutional_trust": 5.2, "life_satisfaction_mean": 6.1}}),
            ("ITC4", "Lombardia", "north", {"economic": {"gdp_per_capita": 41800, "pps_index": 123, "employment_rate": 68.9, "median_income_eur": 39800, "wealth_index": 135, "savings_rate_pct": 12.4}, "cultural": {"PDI": 45, "IDV": 81, "MAS": 54, "UAI": 61, "LTO": 61, "IVR": 48}, "demographic": {"median_age": 45.4, "education_tertiary_pct": 31.8, "unemployment_rate": 4.6, "internet_users_pct": 86.3, "sport_participation_pct": 33.2}, "social": {"interpersonal_trust": 6.7, "institutional_trust": 5.9, "life_satisfaction_mean": 6.8}}),
            ("ITH1", "Provincia Autonoma di Bolzano/Bozen", "north", {"economic": {"gdp_per_capita": 42100, "employment_rate": 69.5, "median_income_eur": 38200, "wealth_index": 139}, "demographic": {"internet_users_pct": 90.1, "education_tertiary_pct": 34.2}, "social": {"interpersonal_trust": 6.3, "institutional_trust": 6.1, "life_satisfaction_mean": 7.0}}),
            ("ITH2", "Provincia Autonoma di Trento", "north", {"economic": {"gdp_per_capita": 38900, "employment_rate": 68.4, "median_income_eur": 36500, "wealth_index": 130}, "demographic": {"internet_users_pct": 89.4, "education_tertiary_pct": 33.5}, "social": {"interpersonal_trust": 6.1, "institutional_trust": 5.9, "life_satisfaction_mean": 6.9}}),
            ("ITH3", "Veneto", "north", {"economic": {"gdp_per_capita": 35700, "employment_rate": 66.8, "median_income_eur": 33500, "wealth_index": 121}, "demographic": {"unemployment_rate": 5.5, "median_age": 45.0}, "social": {"institutional_trust": 5.5, "life_satisfaction_mean": 6.5}}),
            ("ITH4", "Friuli-Venezia Giulia", "north", {"economic": {"gdp_per_capita": 34300, "employment_rate": 63.7, "median_income_eur": 32100, "wealth_index": 114}, "demographic": {"unemployment_rate": 5.7, "internet_users_pct": 86.9}, "social": {"institutional_trust": 5.4, "life_satisfaction_mean": 6.3}}),
            ("ITH5", "Emilia-Romagna", "north", {"economic": {"gdp_per_capita": 36600, "employment_rate": 69.1, "median_income_eur": 34600, "wealth_index": 124}, "demographic": {"unemployment_rate": 5.0, "sport_participation_pct": 34.1}, "social": {"interpersonal_trust": 6.5, "institutional_trust": 5.7, "life_satisfaction_mean": 6.7}}),
            ("ITI1", "Toscana", "center", {"economic": {"gdp_per_capita": 33400, "employment_rate": 61.7, "median_income_eur": 31200, "wealth_index": 112}, "demographic": {"median_age": 46.5, "unemployment_rate": 7.3, "education_tertiary_pct": 29.4}, "social": {"institutional_trust": 4.9, "life_satisfaction_mean": 6.1}}),
            ("ITI2", "Umbria", "center", {"economic": {"gdp_per_capita": 30800, "employment_rate": 59.2, "median_income_eur": 28900, "wealth_index": 103}, "demographic": {"median_age": 47.3, "unemployment_rate": 7.9, "education_tertiary_pct": 26.7}, "social": {"interpersonal_trust": 5.4, "institutional_trust": 4.7, "life_satisfaction_mean": 6.0}}),
            ("ITI3", "Marche", "center", {"economic": {"gdp_per_capita": 31700, "employment_rate": 60.1, "median_income_eur": 29500, "wealth_index": 106}, "demographic": {"median_age": 46.8, "unemployment_rate": 7.1, "sport_participation_pct": 29.9}, "social": {"institutional_trust": 4.8, "life_satisfaction_mean": 6.0}}),
            ("ITI4", "Lazio", "center", {"economic": {"gdp_per_capita": 34100, "pps_index": 108, "employment_rate": 61.3, "median_income_eur": 31100, "wealth_index": 111, "savings_rate_pct": 8.9}, "cultural": {"PDI": 50, "IDV": 74, "MAS": 50, "UAI": 64, "LTO": 56, "IVR": 50}, "demographic": {"median_age": 46.2, "education_tertiary_pct": 28.4, "unemployment_rate": 8.1, "internet_users_pct": 84.2, "sport_participation_pct": 29.7}, "social": {"interpersonal_trust": 5.6, "institutional_trust": 4.9, "life_satisfaction_mean": 6.1}}),
            ("ITF1", "Abruzzo", "south", {"economic": {"gdp_per_capita": 26400, "employment_rate": 51.0, "median_income_eur": 27400, "wealth_index": 83}, "demographic": {"median_age": 45.2, "unemployment_rate": 11.2, "education_tertiary_pct": 22.9}, "social": {"institutional_trust": 4.1, "life_satisfaction_mean": 5.6}}),
            ("ITF2", "Molise", "south", {"economic": {"gdp_per_capita": 25100, "employment_rate": 48.8, "median_income_eur": 26200, "wealth_index": 80}, "demographic": {"median_age": 46.1, "unemployment_rate": 10.7, "internet_users_pct": 78.9}, "social": {"interpersonal_trust": 4.4, "institutional_trust": 3.9, "life_satisfaction_mean": 5.5}}),
            ("ITF3", "Campania", "south", {"economic": {"gdp_per_capita": 22100, "pps_index": 86, "employment_rate": 44.1, "median_income_eur": 25800, "wealth_index": 74, "savings_rate_pct": 5.7}, "cultural": {"PDI": 55, "IDV": 68, "MAS": 48, "UAI": 67, "LTO": 52, "IVR": 45}, "demographic": {"median_age": 44.7, "education_tertiary_pct": 20.6, "unemployment_rate": 17.8, "internet_users_pct": 79.1, "sport_participation_pct": 21.4}, "social": {"interpersonal_trust": 4.2, "institutional_trust": 3.8, "life_satisfaction_mean": 5.4}}),
            ("ITF4", "Puglia", "south", {"economic": {"gdp_per_capita": 23800, "employment_rate": 47.8, "median_income_eur": 26000, "wealth_index": 78}, "demographic": {"median_age": 45.0, "unemployment_rate": 13.8, "education_tertiary_pct": 21.2}, "social": {"institutional_trust": 3.9, "life_satisfaction_mean": 5.3}}),
            ("ITF5", "Basilicata", "south", {"economic": {"gdp_per_capita": 24700, "employment_rate": 49.2, "median_income_eur": 26400, "wealth_index": 79}, "demographic": {"median_age": 46.0, "unemployment_rate": 11.9, "internet_users_pct": 79.8}, "social": {"interpersonal_trust": 4.5, "institutional_trust": 4.0, "life_satisfaction_mean": 5.5}}),
            ("ITF6", "Calabria", "south", {"economic": {"gdp_per_capita": 21400, "employment_rate": 41.6, "median_income_eur": 23900, "wealth_index": 71}, "demographic": {"median_age": 45.8, "unemployment_rate": 16.8, "education_tertiary_pct": 18.9}, "social": {"interpersonal_trust": 3.9, "institutional_trust": 3.4, "life_satisfaction_mean": 5.1}}),
            ("ITG1", "Sicilia", "islands", {"economic": {"gdp_per_capita": 20700, "pps_index": 84, "employment_rate": 43.2, "median_income_eur": 24200, "wealth_index": 69, "savings_rate_pct": 5.1}, "cultural": {"PDI": 58, "IDV": 66, "MAS": 46, "UAI": 69, "LTO": 49, "IVR": 43}, "demographic": {"median_age": 45.9, "education_tertiary_pct": 19.8, "unemployment_rate": 15.9, "internet_users_pct": 77.4, "sport_participation_pct": 20.9}, "social": {"interpersonal_trust": 4.0, "institutional_trust": 3.5, "life_satisfaction_mean": 5.2}}),
            ("ITG2", "Sardegna", "islands", {"economic": {"gdp_per_capita": 22600, "employment_rate": 44.5, "median_income_eur": 24600, "wealth_index": 73}, "demographic": {"median_age": 46.4, "unemployment_rate": 12.9, "internet_users_pct": 79.5, "education_tertiary_pct": 21.8}, "social": {"interpersonal_trust": 4.2, "institutional_trust": 3.7, "life_satisfaction_mean": 5.4}}),
        ]

        profiles: Dict[str, Dict[str, Any]] = {}
        for code, name, zone, overrides in region_specs:
            layers = self._merge_region_layers(templates[zone], overrides)
            profiles[code] = self._make_profile(
                code=code,
                name=name,
                zone=zone,
                economic=layers["economic"],
                cultural=layers["cultural"],
                demographic=layers["demographic"],
                social=layers["social"],
            )

        profiles["IT00"] = self._build_national_profile(profiles)
        return profiles

    def _build_national_profile(self, regional_profiles: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        numeric_layers = {
            "economic": ["gdp_per_capita", "pps_index", "employment_rate", "median_income_eur", "wealth_index", "savings_rate_pct"],
            "cultural": ["PDI", "IDV", "MAS", "UAI", "LTO", "IVR"],
            "demographic": ["median_age", "education_tertiary_pct", "unemployment_rate", "internet_users_pct", "sport_participation_pct"],
            "social": ["interpersonal_trust", "institutional_trust", "life_satisfaction_mean"],
        }

        economic = self._average_layer_values(regional_profiles, "economic", numeric_layers["economic"])
        cultural = self._average_layer_values(regional_profiles, "cultural", numeric_layers["cultural"])
        demographic = self._average_layer_values(regional_profiles, "demographic", numeric_layers["demographic"])
        social = self._average_layer_values(regional_profiles, "social", numeric_layers["social"])

        return self._make_profile(
            code="IT00",
            name="Italia intera",
            zone="national",
            economic=economic,
            cultural=cultural,
            demographic=demographic,
            social=social,
        )

    def _average_layer_values(self, profiles: Dict[str, Dict[str, Any]], layer_name: str, keys: List[str]) -> Dict[str, Any]:
        averaged: Dict[str, Any] = {}
        for key in keys:
            values: List[float] = []
            for profile in profiles.values():
                if profile.get("nuts2_code") == "IT00":
                    continue
                layer = profile.get("layers", {}).get(layer_name, {})
                if layer_name == "cultural":
                    source_values = layer.get("hofstede_6d", {})
                else:
                    source_values = layer.get("indicators", {})
                if key in source_values:
                    try:
                        values.append(float(source_values[key]))
                    except Exception:
                        continue
            if values:
                averaged[key] = round(sum(values) / len(values), 2)
        return averaged

    def _zone_templates(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return {
            "north": {
                "economic": {"gdp_per_capita": 37200, "pps_index": 118, "employment_rate": 66.0, "median_income_eur": 34800, "wealth_index": 125, "savings_rate_pct": 11.2},
                "cultural": {"PDI": 46, "IDV": 79, "MAS": 53, "UAI": 62, "LTO": 60, "IVR": 49},
                "demographic": {"median_age": 45.1, "education_tertiary_pct": 28.9, "unemployment_rate": 5.8, "internet_users_pct": 85.4, "sport_participation_pct": 31.5},
                "social": {"interpersonal_trust": 6.0, "institutional_trust": 5.4, "life_satisfaction_mean": 6.4},
            },
            "center": {
                "economic": {"gdp_per_capita": 31800, "pps_index": 104, "employment_rate": 60.2, "median_income_eur": 30000, "wealth_index": 109, "savings_rate_pct": 8.7},
                "cultural": {"PDI": 49, "IDV": 75, "MAS": 50, "UAI": 64, "LTO": 57, "IVR": 50},
                "demographic": {"median_age": 46.0, "education_tertiary_pct": 26.1, "unemployment_rate": 8.5, "internet_users_pct": 83.2, "sport_participation_pct": 28.8},
                "social": {"interpersonal_trust": 5.3, "institutional_trust": 4.8, "life_satisfaction_mean": 6.0},
            },
            "south": {
                "economic": {"gdp_per_capita": 22800, "pps_index": 87, "employment_rate": 43.6, "median_income_eur": 25600, "wealth_index": 76, "savings_rate_pct": 5.8},
                "cultural": {"PDI": 56, "IDV": 67, "MAS": 47, "UAI": 68, "LTO": 51, "IVR": 45},
                "demographic": {"median_age": 45.0, "education_tertiary_pct": 20.4, "unemployment_rate": 16.1, "internet_users_pct": 78.3, "sport_participation_pct": 21.1},
                "social": {"interpersonal_trust": 4.3, "institutional_trust": 3.7, "life_satisfaction_mean": 5.4},
            },
            "islands": {
                "economic": {"gdp_per_capita": 21900, "pps_index": 85, "employment_rate": 42.7, "median_income_eur": 24800, "wealth_index": 72, "savings_rate_pct": 5.4},
                "cultural": {"PDI": 57, "IDV": 66, "MAS": 46, "UAI": 69, "LTO": 50, "IVR": 44},
                "demographic": {"median_age": 45.8, "education_tertiary_pct": 19.9, "unemployment_rate": 15.6, "internet_users_pct": 77.6, "sport_participation_pct": 20.4},
                "social": {"interpersonal_trust": 4.1, "institutional_trust": 3.5, "life_satisfaction_mean": 5.2},
            },
        }

    def _merge_region_layers(self, template: Dict[str, Dict[str, Any]], overrides: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for layer_name in ("economic", "cultural", "demographic", "social"):
            layer_values = dict(template.get(layer_name, {}))
            layer_values.update(overrides.get(layer_name, {}))
            merged[layer_name] = layer_values
        return merged

    def _make_profile(
        self,
        code: str,
        name: str,
        zone: str,
        economic: Dict[str, Any],
        cultural: Dict[str, Any],
        demographic: Dict[str, Any],
        social: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "nuts2_code": code,
            "name": name,
            "cultural_zone": zone,
            "layers": {
                "economic": {
                    "source": "Eurostat SDMX + Banca d'Italia IBF",
                    "indicators": economic,
                },
                "cultural": {
                    "source": "Hofstede 6D + Schwartz/ESS Round 10",
                    "hofstede_6d": cultural,
                    "schwartz": {
                        "dominant_values": ["security", "benevolence", "self-direction"] if zone == "north" else (["balance", "pragmatism", "benevolence"] if zone == "national" else ["tradition", "conformity", "benevolence"]),
                        "source": "ESS Round 10 / starter snapshot",
                    },
                },
                "demographic": {
                    "source": "ISTAT Noi Italia / BES",
                    "indicators": demographic,
                },
                "social": {
                    "source": "ESS Round 10",
                    "indicators": social,
                },
            },
            "derived": self._derive_behavioral_profile({
                "layers": {
                    "economic": {"indicators": economic},
                    "cultural": {"hofstede_6d": cultural},
                    "demographic": {"indicators": demographic},
                    "social": {"indicators": social},
                },
            }),
        }

    def _safe_number(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _derive_behavioral_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        layers = profile.get("layers", {})
        economic = layers.get("economic", {}).get("indicators", {})
        cultural = layers.get("cultural", {}).get("hofstede_6d", {})
        demographic = layers.get("demographic", {}).get("indicators", {})
        social = layers.get("social", {}).get("indicators", {})

        unemployment = self._safe_number(demographic.get("unemployment_rate"), 0.0)
        internet = self._safe_number(demographic.get("internet_users_pct"), 0.0)
        employment = self._safe_number(economic.get("employment_rate"), 0.0)
        income = self._safe_number(economic.get("median_income_eur"), 0.0)
        pdi = self._safe_number(cultural.get("PDI"), 50.0)
        idv = self._safe_number(cultural.get("IDV"), 50.0)
        trust_people = self._safe_number(social.get("interpersonal_trust"), 5.0)
        trust_institutions = self._safe_number(social.get("institutional_trust"), 5.0)
        life_satisfaction = self._safe_number(social.get("life_satisfaction_mean"), 5.5)

        activity_multiplier = self._clamp(
            0.88 + (internet - 75.0) / 250.0 + (employment - 50.0) / 300.0 - unemployment / 250.0,
            0.8,
            1.2,
        )
        response_delay_multiplier = self._clamp(1.15 - trust_institutions / 20.0, 0.75, 1.2)
        influence_multiplier = self._clamp(0.9 + (60.0 - pdi) / 200.0 + (idv - 70.0) / 300.0, 0.8, 1.2)
        sentiment_bias = self._clamp((life_satisfaction - 5.5) / 10.0 + (trust_people - 5.0) / 20.0, -0.3, 0.3)

        if trust_institutions < 4.5 or unemployment > 12:
            stance = "opposing"
        elif trust_institutions > 5.5 and life_satisfaction > 6:
            stance = "supportive"
        else:
            stance = "neutral"

        communication_style = "riservato e diretto" if pdi <= 48 else "più espressivo e relazionale"
        if income > 35000:
            communication_style = f"{communication_style}, con forte attenzione al pragmatismo economico"

        return {
            "activity_multiplier": round(activity_multiplier, 3),
            "response_delay_multiplier": round(response_delay_multiplier, 3),
            "influence_multiplier": round(influence_multiplier, 3),
            "sentiment_bias": round(sentiment_bias, 3),
            "stance": stance,
            "communication_style": communication_style,
            "economic_pressure": round(self._clamp(1.2 - (income / 50000.0), 0.7, 1.2), 3),
        }

    @property
    def available_regions(self) -> List[str]:
        return list(self._profiles.keys())

    @property
    def is_loaded(self) -> bool:
        return self._loaded and bool(self._profiles)

    def list_regions(self) -> List[Dict[str, Any]]:
        ordered_codes = sorted(self._profiles.keys())
        if "IT00" in ordered_codes:
            ordered_codes.remove("IT00")
            ordered_codes.insert(0, "IT00")
        return [self._region_overview(self._profiles[code]) for code in ordered_codes]

    def _region_overview(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "nuts2_code": profile.get("nuts2_code"),
            "name": profile.get("name"),
            "cultural_zone": profile.get("cultural_zone"),
            "summary": self._build_short_summary(profile),
            "derived": profile.get("derived", {}),
        }

    def get_profile(self, nuts2_code: str) -> Optional[Dict[str, Any]]:
        profile = self._profiles.get(nuts2_code)
        return copy.deepcopy(profile) if profile else None

    def get_region_name(self, nuts2_code: str) -> str:
        profile = self._profiles.get(nuts2_code, {})
        return profile.get("name", nuts2_code)

    def get_cultural_zone(self, nuts2_code: str) -> str:
        profile = self._profiles.get(nuts2_code, {})
        return profile.get("cultural_zone", "center")

    def get_calibration_text(self, nuts2_code: str) -> Optional[str]:
        profile = self._profiles.get(nuts2_code)
        if not profile:
            return None
        return self._build_text(profile)

    def build_region_explanation(self, nuts2_code: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(nuts2_code)
        if not profile:
            return None

        return {
            "nuts2_code": profile.get("nuts2_code"),
            "name": profile.get("name"),
            "cultural_zone": profile.get("cultural_zone"),
            "layers": profile.get("layers", {}),
            "derived": profile.get("derived", {}),
            "summary": self._build_short_summary(profile),
            "text": self._build_text(profile),
        }

    def build_agent_calibration_context(self, nuts2_code: str) -> str:
        profile = self._profiles.get(nuts2_code)
        if not profile:
            return ""
        return self._build_text(profile)

    def _build_short_summary(self, profile: Dict[str, Any]) -> str:
        derived = profile.get("derived", {})
        return (
            f"{profile.get('name')} ({profile.get('nuts2_code')}), zona {profile.get('cultural_zone')}. "
            f"Stile: {derived.get('communication_style', 'n/d')}. "
            f"Attività ×{derived.get('activity_multiplier', 1.0)}, ritardo ×{derived.get('response_delay_multiplier', 1.0)}, "
            f"influenza ×{derived.get('influence_multiplier', 1.0)}."
        )

    def _build_text(self, profile: Dict[str, Any]) -> str:
        layers = profile.get("layers", {})
        derived = profile.get("derived", {})

        economic = layers.get("economic", {}).get("indicators", {})
        cultural = layers.get("cultural", {}).get("hofstede_6d", {})
        demographic = layers.get("demographic", {}).get("indicators", {})
        social = layers.get("social", {}).get("indicators", {})

        return (
            f"[ICF {profile.get('name')} — {profile.get('nuts2_code')}]\n"
            f"Zona culturale: {profile.get('cultural_zone')}\n\n"
            f"Economico: PIL pro capite €{economic.get('gdp_per_capita', 'n/d')}, PPS {economic.get('pps_index', 'n/d')}, "
            f"occupazione {economic.get('employment_rate', 'n/d')}%, reddito mediano €{economic.get('median_income_eur', 'n/d')}, "
            f"risparmio {economic.get('savings_rate_pct', 'n/d')}%.\n"
            f"Culturale: PDI {cultural.get('PDI', 'n/d')}, IDV {cultural.get('IDV', 'n/d')}, MAS {cultural.get('MAS', 'n/d')}, "
            f"UAI {cultural.get('UAI', 'n/d')}, LTO {cultural.get('LTO', 'n/d')}, IVR {cultural.get('IVR', 'n/d')}.\n"
            f"Demografico: età mediana {demographic.get('median_age', 'n/d')}, istruzione terziaria {demographic.get('education_tertiary_pct', 'n/d')}%, "
            f"disoccupazione {demographic.get('unemployment_rate', 'n/d')}%, utenti internet {demographic.get('internet_users_pct', 'n/d')}%, "
            f"sport {demographic.get('sport_participation_pct', 'n/d')}%.\n"
            f"Sociale: fiducia interpersonale {social.get('interpersonal_trust', 'n/d')}, fiducia istituzionale {social.get('institutional_trust', 'n/d')}, "
            f"soddisfazione vita {social.get('life_satisfaction_mean', 'n/d')}.\n\n"
            f"Indicazioni comportamentali: attività ×{derived.get('activity_multiplier', 1.0)}, ritardo risposta ×{derived.get('response_delay_multiplier', 1.0)}, "
            f"influenza ×{derived.get('influence_multiplier', 1.0)}, stance prevalente {derived.get('stance', 'neutral')}, "
            f"stile comunicativo {derived.get('communication_style', 'n/d')}.\n"
            f"Fonti: {layers.get('economic', {}).get('source', 'n/d')} | {layers.get('cultural', {}).get('source', 'n/d')} | "
            f"{layers.get('demographic', {}).get('source', 'n/d')} | {layers.get('social', {}).get('source', 'n/d')}"
        )
