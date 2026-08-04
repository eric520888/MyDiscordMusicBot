export type Locale = "zh-TW" | "zh-CN" | "en-US";

export type LobbyPlayer = {
  player_id: string;
  seat: number;
  display_name: string;
  status: "alive" | "dead";
  connected: boolean;
  ready: boolean;
  spectator: boolean;
};

export type ProjectedPlayer = LobbyPlayer & {
  vote_enabled: boolean;
  revealed_role_id: string | null;
};

export type ProjectedEvent = {
  sequence: number;
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
};

export type ActivityBoardOption = {
  board_id: "classic" | "beginner" | "power";
  preview_player_count: number;
  role_ids: string[];
};

export type GameProjection = {
  game_id: string;
  viewer_player_id: string;
  board_id: string;
  phase: "starting" | "night_actions" | "night_witch" | "day" | "role_shoot" | "ended";
  round_number: number;
  revision: number;
  phase_started_at: string | null;
  phase_ends_at: string | null;
  settings: { reveal_roles_on_death: boolean };
  players: ProjectedPlayer[];
  self_role_state: { role_id: string; resources: Record<string, boolean | number> } | null;
  wolf_team_player_ids: string[];
  pending_decisions: Array<Record<string, unknown>>;
  events: ProjectedEvent[];
  winner: "wolf" | "good" | "third_party" | null;
  ended_reason: string | null;
};

export type Snapshot = {
  server_time: string;
  self_player_id: string;
  is_host: boolean;
  room: {
    room_id: string;
    revision: number;
    host_player_id: string;
    selected_board_id: ActivityBoardOption["board_id"];
    board_options: ActivityBoardOption[];
    settings: {
      reveal_roles_on_death: boolean;
      locked: boolean;
    };
    players: LobbyPlayer[];
  };
  game: GameProjection | null;
};
