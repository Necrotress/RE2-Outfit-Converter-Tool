"""Character profiles for Claire / Leon convert pipelines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterProfile:
    """Roots and ID families for one playable character."""

    key: str                       # "claire" | "leon"
    display_name: str
    player_root: str               # pl1000 / pl0000
    ui_row: str                    # "01" Claire / "00" Leon in ui0601_{row}_{id}
    figure_prefix: str             # figurescene_pl1000 / figurescene_pl0000
    face_ids: frozenset[str]
    hair_mesh_ids: frozenset[str]
    exclusive_part_ids: frozenset[str]
    shared_ids: frozenset[str]
    # Default shared hair folder used by redirect templates.
    default_hair_id: str
    # Extra figure gallery ids that belong to this character.
    extra_figure_ids: frozenset[str]

    @property
    def parts_dir(self) -> str:
        return (
            "natives/x64/objectroot/prefab/character/survivor/parts/"
            f"{self.player_root}"
        )

    @property
    def mesh_roots(self) -> tuple[str, str]:
        return (
            f"natives/x64/sectionroot/character/player/{self.player_root}",
            f"natives/x64/streaming/sectionroot/character/player/"
            f"{self.player_root}",
        )


CLAIRE_PROFILE = CharacterProfile(
    key="claire",
    display_name="Claire",
    player_root="pl1000",
    ui_row="01",
    figure_prefix="pl1000",
    face_ids=frozenset({"pl1050", "pl1057"}),
    hair_mesh_ids=frozenset({"pl1070", "pl1071", "pl1075"}),
    exclusive_part_ids=frozenset({"pl1071", "pl1075"}),
    shared_ids=frozenset({
        "pl1050", "pl1057", "pl1070", "pl1071", "pl1075",
    }),
    default_hair_id="pl1070",
    extra_figure_ids=frozenset({"10", "11", "12", "13"}),
)

LEON_PROFILE = CharacterProfile(
    key="leon",
    display_name="Leon",
    player_root="pl0000",
    ui_row="00",
    figure_prefix="pl0000",
    face_ids=frozenset({"pl0050", "pl0057"}),
    hair_mesh_ids=frozenset({"pl0070", "pl0074", "pl0075"}),
    exclusive_part_ids=frozenset({"pl0074", "pl0075"}),
    shared_ids=frozenset({
        "pl0050", "pl0057", "pl0070", "pl0074", "pl0075",
    }),
    default_hair_id="pl0070",
    extra_figure_ids=frozenset({"10", "11", "13"}),
)

PROFILES: dict[str, CharacterProfile] = {
    CLAIRE_PROFILE.key: CLAIRE_PROFILE,
    LEON_PROFILE.key: LEON_PROFILE,
}


def profile_for_key(key: str) -> CharacterProfile:
    try:
        return PROFILES[key]
    except KeyError as e:
        raise KeyError(f"Unknown character profile: {key}") from e
