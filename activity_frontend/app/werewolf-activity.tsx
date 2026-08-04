"use client";

import { DiscordSDK } from "@discord/embedded-app-sdk";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chooseLocale, translate } from "./i18n";
import type {
  ActivityBoardOption,
  GameProjection,
  Locale,
  LobbyPlayer,
  ProjectedEvent,
  ProjectedPlayer,
  Snapshot,
} from "./types";

type ConnectionStage = "connecting" | "connected" | "error";
type SocketCommand = {
  type: string;
  request_id: string;
  payload: Record<string, unknown>;
};

const roleMarks: Record<string, string> = {
  werewolf: "狼",
  villager: "民",
  seer: "預",
  witch: "巫",
  hunter: "獵",
};

const guideRoles = [
  { roleId: "werewolf", camp: "wolf" },
  { roleId: "villager", camp: "villager" },
  { roleId: "seer", camp: "good" },
  { roleId: "witch", camp: "good" },
  { roleId: "hunter", camp: "good" },
] as const;

function roleName(locale: Locale, roleId?: string | null) {
  return roleId ? translate(locale, `role.${roleId}`) : "—";
}

function roleDescription(locale: Locale, roleId?: string | null) {
  return roleId ? translate(locale, `role.${roleId}.desc`) : "";
}

function errorMessage(value: unknown): string {
  if (value instanceof Error) return value.message;
  if (typeof value === "string") return value;
  return "Unknown error";
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (typeof data === "object" && data !== null && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "object" && detail !== null && "message" in detail) {
        throw new Error(String((detail as { message: unknown }).message));
      }
    }
    throw new Error(`Request failed (${response.status})`);
  }
  return data as T;
}

function withTimeout<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error("DISCORD_TIMEOUT")), milliseconds)),
  ]);
}

function MoonMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "moon-mark moon-mark--compact" : "moon-mark"} aria-hidden="true">
      <span className="moon-mark__disc" />
      <span className="moon-mark__cut" />
      <span className="moon-mark__eye" />
    </div>
  );
}

function LocaleSelect({ locale, onChange }: { locale: Locale; onChange: (value: Locale) => void }) {
  return (
    <label className="locale-control">
      <span className="sr-only">Language</span>
      <select value={locale} onChange={(event) => onChange(event.target.value as Locale)}>
        <option value="zh-TW">繁中</option>
        <option value="zh-CN">简中</option>
        <option value="en-US">EN</option>
      </select>
    </label>
  );
}

function BrandHeader({
  locale,
  connection,
  onOpenGuide,
}: {
  locale: Locale;
  connection: ConnectionStage;
  onOpenGuide: () => void;
}) {
  return (
    <header className="brand-header">
      <div className="brand-header__identity">
        <MoonMark compact />
        <div>
          <span className="eyebrow">{translate(locale, "brand.eyebrow")}</span>
          <strong>{translate(locale, "brand.title")}</strong>
        </div>
      </div>
      <div className="brand-header__actions">
        <button type="button" className="guide-button" onClick={onOpenGuide}>
          {translate(locale, "guide.open")}
        </button>
        <span className={`connection-dot connection-dot--${connection}`} aria-label={connection} />
      </div>
    </header>
  );
}

function LobbySeat({ player, snapshot, locale }: { player: LobbyPlayer | null; snapshot: Snapshot; locale: Locale }) {
  if (!player) {
    return (
      <div className="seat-card seat-card--empty">
        <span className="seat-card__number">—</span>
        <span>{translate(locale, "lobby.emptySeat")}</span>
      </div>
    );
  }
  const isSelf = player.player_id === snapshot.self_player_id;
  const isHost = player.player_id === snapshot.room.host_player_id;
  return (
    <div className={`seat-card ${player.ready ? "seat-card--ready" : ""} ${isSelf ? "seat-card--self" : ""}`}>
      <span className="seat-card__number">{String(player.seat).padStart(2, "0")}</span>
      <span className="seat-card__avatar">{player.display_name.slice(0, 1).toUpperCase()}</span>
      <span className="seat-card__body">
        <strong>{player.display_name}</strong>
        <small>{player.ready ? translate(locale, "lobby.ready") : translate(locale, "lobby.notReady")}</small>
      </span>
      <span className="seat-card__badges">
        {isHost && <em>{translate(locale, "lobby.host")}</em>}
        {isSelf && <em>{translate(locale, "lobby.you")}</em>}
      </span>
    </div>
  );
}

function BoardComposition({ option, locale }: { option: ActivityBoardOption; locale: Locale }) {
  const counts = option.role_ids.reduce<Record<string, number>>((result, roleId) => {
    result[roleId] = (result[roleId] ?? 0) + 1;
    return result;
  }, {});
  return (
    <div className="board-composition" aria-label={translate(locale, "guide.composition")}>
      {Object.entries(counts).map(([roleId, count]) => (
        <span key={roleId} className={`composition-chip composition-chip--${roleId}`}>
          <b>{roleMarks[roleId] ?? "?"}</b>
          {roleName(locale, roleId)} × {count}
        </span>
      ))}
    </div>
  );
}

function BoardOptionButton({
  option,
  locale,
  selected,
  disabled,
  onSelect,
}: {
  option: ActivityBoardOption;
  locale: Locale;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`board-option ${selected ? "board-option--selected" : ""}`}
      disabled={disabled}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="board-option__heading">
        <strong>{translate(locale, `board.${option.board_id}.name`)}</strong>
        {selected && <em>{translate(locale, "guide.selected")}</em>}
      </span>
      <small>{translate(locale, `board.${option.board_id}.style`)}</small>
      <p>{translate(locale, `board.${option.board_id}.desc`)}</p>
      <BoardComposition option={option} locale={locale} />
    </button>
  );
}

function GameGuide({
  locale,
  boardOptions,
  onClose,
}: {
  locale: Locale;
  boardOptions: ActivityBoardOption[];
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"boards" | "roles">(boardOptions.length ? "boards" : "roles");
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="guide-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="guide-dialog" role="dialog" aria-modal="true" aria-labelledby="guide-title">
        <header className="guide-dialog__header">
          <div>
            <span className="eyebrow">{translate(locale, "guide.eyebrow")}</span>
            <h2 id="guide-title">{translate(locale, "guide.title")}</h2>
          </div>
          <button type="button" className="guide-dialog__close" onClick={onClose} aria-label={translate(locale, "guide.close")}>
            ×
          </button>
        </header>
        <div className="guide-tabs" role="tablist" aria-label={translate(locale, "guide.title")}>
          <button type="button" role="tab" aria-selected={tab === "boards"} disabled={!boardOptions.length} onClick={() => setTab("boards")}>
            {translate(locale, "guide.boards")}
          </button>
          <button type="button" role="tab" aria-selected={tab === "roles"} onClick={() => setTab("roles")}>
            {translate(locale, "guide.roles")}
          </button>
        </div>

        {tab === "boards" ? (
          <div className="guide-board-grid">
            {boardOptions.map((option) => (
              <article key={option.board_id} className="guide-board-card">
                <span className="eyebrow">{translate(locale, `board.${option.board_id}.style`)}</span>
                <h3>{translate(locale, `board.${option.board_id}.name`)}</h3>
                <p>{translate(locale, `board.${option.board_id}.long`)}</p>
                <small>{translate(locale, "guide.previewPlayers", { count: option.preview_player_count })}</small>
                <BoardComposition option={option} locale={locale} />
              </article>
            ))}
          </div>
        ) : (
          <div className="guide-role-grid">
            {guideRoles.map(({ roleId, camp }) => (
              <article key={roleId} className={`guide-role-card guide-role-card--${roleId}`}>
                <div className="guide-role-card__title">
                  <span>{roleMarks[roleId] ?? "?"}</span>
                  <div>
                    <small>{translate(locale, `guide.camp.${camp}`)}</small>
                    <h3>{roleName(locale, roleId)}</h3>
                  </div>
                </div>
                <p>{roleDescription(locale, roleId)}</p>
                <dl>
                  <div><dt>{translate(locale, "guide.timing")}</dt><dd>{translate(locale, `role.${roleId}.timing`)}</dd></div>
                  <div><dt>{translate(locale, "guide.goal")}</dt><dd>{translate(locale, `role.${roleId}.goal`)}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function LobbyScreen({
  snapshot,
  locale,
  send,
}: {
  snapshot: Snapshot;
  locale: Locale;
  send: (type: string, payload?: Record<string, unknown>) => void;
}) {
  const self = snapshot.room.players.find((player) => player.player_id === snapshot.self_player_id);
  const seated = snapshot.room.players.filter((player) => !player.spectator);
  const hasEnoughPlayers = seated.length >= 3;
  const everyoneReady = hasEnoughPlayers && seated.every((player) => player.ready);
  const seats = Array.from({ length: 12 }, (_, index) => seated.find((player) => player.seat === index + 1) ?? null);
  const startLabel = !hasEnoughPlayers
    ? "lobby.needPlayers"
    : everyoneReady
      ? "lobby.start"
      : "lobby.waitingReady";

  return (
    <main className="lobby-layout">
      <section className="lobby-hero">
        <div>
          <span className="eyebrow">{translate(locale, "lobby.title")}</span>
          <h1>{translate(locale, "brand.title")}</h1>
          <p>{translate(locale, "brand.tagline")}</p>
        </div>
        <div className="player-count" aria-label={`${seated.length}/12`}>
          <strong>{seated.length}</strong>
          <span>/ 12</span>
        </div>
      </section>

      <section className="lobby-main panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">{translate(locale, "lobby.players")}</span>
            <h2>{translate(locale, "lobby.subtitle")}</h2>
          </div>
          <span className="room-code">{snapshot.room.room_id.slice(-6).toUpperCase()}</span>
        </div>
        <div className="seat-grid">
          {seats.map((player, index) => (
            <LobbySeat key={player?.player_id ?? `empty-${index}`} player={player} snapshot={snapshot} locale={locale} />
          ))}
        </div>
      </section>

      <aside className="lobby-controls panel">
        <section className="board-picker">
          <div className="board-picker__heading">
            <div>
              <span className="eyebrow">{translate(locale, "settings.board")}</span>
              <h2>{translate(locale, "settings.chooseBoard")}</h2>
            </div>
            {!snapshot.is_host && <small>{translate(locale, "guide.hostOnly")}</small>}
          </div>
          <div className="board-options">
            {snapshot.room.board_options.map((option) => (
              <BoardOptionButton
                key={option.board_id}
                option={option}
                locale={locale}
                selected={option.board_id === snapshot.room.selected_board_id}
                disabled={!snapshot.is_host}
                onSelect={() => send("set_board", { board_id: option.board_id })}
              />
            ))}
          </div>
          <small className="board-picker__note">
            {translate(locale, "settings.boardReadyReset")}
          </small>
        </section>

        <div className="death-reveal-heading">
          <span className="eyebrow">{translate(locale, "settings.title")}</span>
          <h2>{translate(locale, "settings.deathReveal")}</h2>
        </div>
        <button
          type="button"
          className={`setting-toggle ${snapshot.room.settings.reveal_roles_on_death ? "setting-toggle--on" : ""}`}
          disabled={!snapshot.is_host}
          onClick={() =>
            send("set_death_reveal", {
              reveal_roles_on_death: !snapshot.room.settings.reveal_roles_on_death,
            })
          }
        >
          <span className="setting-toggle__track"><span /></span>
          <span>
            <strong>
              {translate(
                locale,
                snapshot.room.settings.reveal_roles_on_death
                  ? "settings.deathRevealOn"
                  : "settings.deathRevealOff",
              )}
            </strong>
            <small>{translate(locale, "settings.lockHint")}</small>
          </span>
        </button>

        <div className="lobby-actions">
          <button
            type="button"
            className={`button ${self?.ready ? "button--quiet" : "button--primary"}`}
            onClick={() => send("set_ready", { ready: !self?.ready })}
          >
            {translate(locale, self?.ready ? "lobby.cancelReady" : "lobby.readyAction")}
          </button>
          {snapshot.is_host && (
            <button
              type="button"
              className="button button--danger"
              disabled={!everyoneReady}
              onClick={() => send("start_game")}
            >
              {translate(locale, startLabel)}
            </button>
          )}
        </div>
      </aside>
    </main>
  );
}

function RoleReveal({ snapshot, locale, send }: { snapshot: Snapshot; locale: Locale; send: (type: string) => void }) {
  const roleId = snapshot.game?.self_role_state?.role_id;
  return (
    <main className="reveal-layout">
      <section className="reveal-copy">
        <span className="eyebrow">{translate(locale, "phase.starting")}</span>
        <h1>{translate(locale, "role.yours")}</h1>
        <p>{translate(locale, "role.revealHint")}</p>
      </section>
      <section className={`role-card role-card--${roleId ?? "unknown"}`}>
        <span className="role-card__moon" />
        <span className="role-card__mark">{roleMarks[roleId ?? ""] ?? "?"}</span>
        <div>
          <span className="eyebrow">{translate(locale, "role.yours")}</span>
          <h2>{roleName(locale, roleId)}</h2>
          <p>{roleDescription(locale, roleId)}</p>
        </div>
      </section>
      {snapshot.is_host ? (
        <button type="button" className="button button--danger reveal-advance" onClick={() => send("advance_first_night")}>
          {translate(locale, "role.advance")}
        </button>
      ) : (
        <p className="waiting-copy">{translate(locale, "action.waiting")}</p>
      )}
    </main>
  );
}

function PlayerToken({
  player,
  selected,
  disabled,
  onClick,
  locale,
}: {
  player: ProjectedPlayer;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  locale: Locale;
}) {
  return (
    <button
      type="button"
      className={`player-token ${selected ? "player-token--selected" : ""} ${player.status === "dead" ? "player-token--dead" : ""}`}
      disabled={disabled || player.status === "dead"}
      onClick={onClick}
    >
      <span className="player-token__seat">{player.seat}</span>
      <span className="player-token__avatar">{player.display_name.slice(0, 1).toUpperCase()}</span>
      <strong>{player.display_name}</strong>
      <small>{player.status === "dead" ? translate(locale, "game.dead") : translate(locale, "game.alive")}</small>
      {player.revealed_role_id && <em>{roleName(locale, player.revealed_role_id)}</em>}
    </button>
  );
}

function eventText(event: ProjectedEvent, locale: Locale, game: GameProjection): string {
  const payload = event.payload;
  const playerName = (id: unknown) =>
    game.players.find((player) => player.player_id === id)?.display_name ?? "?";
  if (event.event_type === "seer_result") {
    const alignment = payload.alignment === "wolf" ? roleName(locale, "werewolf") : locale === "en-US" ? "Good" : "好人";
    return `${playerName(payload.target_player_id)} · ${alignment}`;
  }
  if (event.event_type === "player_died") {
    const names = Array.isArray(payload.player_ids)
      ? payload.player_ids.map(playerName).join("、")
      : playerName(payload.player_id);
    return `${translate(locale, "event.player_died")} ${names}`;
  }
  return translate(locale, `event.${event.event_type}`);
}

function PhaseTimer({ endsAt }: { endsAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  if (!endsAt) return null;
  const seconds = Math.max(0, Math.ceil((new Date(endsAt).getTime() - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return <time className="phase-timer" dateTime={endsAt}>{minutes}:{String(remainder).padStart(2, "0")}</time>;
}

function GameBoard({
  snapshot,
  locale,
  sendAction,
}: {
  snapshot: Snapshot;
  locale: Locale;
  sendAction: (actionId: string, targets?: string[]) => void;
}) {
  const game = snapshot.game!;
  const self = game.players.find((player) => player.player_id === snapshot.self_player_id)!;
  const roleId = game.self_role_state?.role_id;
  const alive = game.players.filter((player) => player.status === "alive");
  const decision = game.pending_decisions[0];
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<"poison" | "default">("default");

  let actionTitle = translate(locale, "action.waiting");
  let actionId: string | null = null;
  let targets: ProjectedPlayer[] = [];
  let canSkip = false;

  if (game.phase === "night_actions" && self.status === "alive" && roleId === "werewolf") {
    actionTitle = translate(locale, "action.wolfKill");
    actionId = "wolf_kill";
    targets = alive.filter((player) => !game.wolf_team_player_ids.includes(player.player_id));
  } else if (game.phase === "night_actions" && self.status === "alive" && roleId === "seer") {
    actionTitle = translate(locale, "action.seerCheck");
    actionId = "seer_check";
    targets = alive.filter((player) => player.player_id !== self.player_id);
  } else if (game.phase === "night_witch" && decision && roleId === "witch") {
    const wolfTargets = Array.isArray(decision.wolf_target_ids)
      ? decision.wolf_target_ids.filter((value): value is string => typeof value === "string")
      : [];
    actionTitle = translate(locale, mode === "poison" ? "action.witchPoison" : "action.witchSave");
    actionId = mode === "poison" ? "witch_poison" : "witch_antidote";
    targets = mode === "poison" ? alive : alive.filter((player) => wolfTargets.includes(player.player_id));
    canSkip = true;
  } else if (game.phase === "day" && self.status === "alive" && self.vote_enabled) {
    actionTitle = translate(locale, "action.vote");
    actionId = "vote";
    targets = alive;
    canSkip = true;
  } else if (game.phase === "role_shoot" && decision) {
    actionTitle = translate(locale, "action.shoot");
    actionId = "hunter_shoot";
    targets = alive;
    canSkip = true;
  }

  const recentEvents = [...game.events].slice(-7).reverse();
  const isNight = game.phase.startsWith("night");

  return (
    <main className={`game-layout ${isNight ? "game-layout--night" : "game-layout--day"}`}>
      <section className="game-stage panel">
        <div className="phase-heading">
          <div>
            <span className="eyebrow">{translate(locale, "game.round", { round: game.round_number })}</span>
            <h1>{translate(locale, `phase.${game.phase}`)}</h1>
          </div>
          <div className="phase-meta">
            <PhaseTimer endsAt={game.phase_ends_at} />
            <div className={`role-chip role-chip--${roleId}`}>
              <span>{roleMarks[roleId ?? ""] ?? "?"}</span>
              <div><small>{translate(locale, "role.yours")}</small><strong>{roleName(locale, roleId)}</strong></div>
            </div>
          </div>
        </div>

        {game.phase === "ended" ? (
          <div className="winner-panel">
            <MoonMark />
            <span className="eyebrow">{translate(locale, "phase.ended")}</span>
            <h2>{translate(locale, `game.winner.${game.winner ?? "good"}`)}</h2>
          </div>
        ) : (
          <div className="action-panel">
            <div className="action-panel__heading">
              <span className="eyebrow">{actionId ? translate(locale, "action.chooseTarget") : ""}</span>
              <h2>{actionTitle}</h2>
            </div>

            {game.phase === "night_witch" && decision && roleId === "witch" && (
              <div className="mode-tabs">
                <button type="button" className={mode === "default" ? "active" : ""} onClick={() => setMode("default")}>
                  {translate(locale, "action.witchSave")}
                </button>
                <button type="button" className={mode === "poison" ? "active" : ""} onClick={() => setMode("poison")}>
                  {translate(locale, "action.witchPoison")}
                </button>
              </div>
            )}

            {actionId && (
              <>
                <div className="target-grid">
                  {targets.map((player) => (
                    <PlayerToken
                      key={player.player_id}
                      player={player}
                      selected={selected === player.player_id}
                      onClick={() => setSelected(player.player_id)}
                      locale={locale}
                    />
                  ))}
                </div>
                <div className="action-buttons">
                  {canSkip && (
                    <button type="button" className="button button--quiet" onClick={() => sendAction("abstain", [])}>
                      {translate(locale, "action.skip")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="button button--danger"
                    disabled={!selected}
                    onClick={() => selected && sendAction(actionId, [selected])}
                  >
                    {actionTitle}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      <aside className="roster-panel panel">
        <div className="section-heading">
          <div><span className="eyebrow">{translate(locale, "lobby.players")}</span><h2>{alive.length} / {game.players.length}</h2></div>
        </div>
        <div className="compact-roster">
          {game.players.map((player) => (
            <PlayerToken key={player.player_id} player={player} disabled locale={locale} />
          ))}
        </div>
      </aside>

      <aside className="timeline-panel panel">
        <div className="section-heading">
          <div><span className="eyebrow">LIVE</span><h2>{translate(locale, "game.timeline")}</h2></div>
        </div>
        <ol className="timeline">
          {recentEvents.length ? recentEvents.map((event) => (
            <li key={`${event.sequence}-${event.event_type}`}>
              <span>{String(event.sequence).padStart(2, "0")}</span>
              <p>{eventText(event, locale, game)}</p>
            </li>
          )) : <li className="timeline__empty">{translate(locale, "game.noEvents")}</li>}
        </ol>
      </aside>
    </main>
  );
}

export function WerewolfActivity() {
  const [locale, setLocale] = useState<Locale>("zh-TW");
  const [stage, setStage] = useState<ConnectionStage>("connecting");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [fatalError, setFatalError] = useState("");
  const [toast, setToast] = useState("");
  const [guideOpen, setGuideOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: number | undefined;
    async function boot() {
      try {
        const config = await requestJson<{ discord_client_id: string }>("/api/config");
        if (!config.discord_client_id) throw new Error("Discord Client ID 尚未設定");
        const discord = new DiscordSDK(config.discord_client_id, { disableConsoleLogOverride: true });
        await withTimeout(discord.ready(), 12000);
        const localeResult = await discord.commands.userSettingsGetLocale().catch(() => null);
        const chosenLocale = chooseLocale(localeResult?.locale ?? navigator.language);
        if (!disposed) setLocale(chosenLocale);
        const { code } = await discord.commands.authorize({
          client_id: config.discord_client_id,
          response_type: "code",
          state: crypto.randomUUID(),
          prompt: "none",
          scope: ["identify"],
        });
        const authResult = await requestJson<{
          access_token: string;
          session_token: string;
        }>("/api/auth/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        await discord.commands.authenticate({ access_token: authResult.access_token });
        if (!discord.channelId) throw new Error("Discord 頻道資訊不存在");
        const context = {
          instance_id: discord.instanceId,
          channel_id: discord.channelId,
          guild_id: discord.guildId,
          locale: chosenLocale,
        };
        const connected = await requestJson<Snapshot>("/api/rooms/connect", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${authResult.session_token}`,
          },
          body: JSON.stringify(context),
        });
        if (disposed) return;
        setSnapshot(connected);
        setStage("connected");

        const openSocket = () => {
          if (disposed) return;
          const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
          const query = new URLSearchParams({
            token: authResult.session_token,
            instance_id: context.instance_id,
            channel_id: context.channel_id,
            locale: context.locale,
          });
          if (context.guild_id) query.set("guild_id", context.guild_id);
          const socket = new WebSocket(`${protocol}//${window.location.host}/ws/rooms/${connected.room.room_id}?${query}`);
          socketRef.current = socket;
          socket.onopen = () => !disposed && setStage("connected");
          socket.onmessage = (event) => {
            const message: unknown = JSON.parse(String(event.data));
            if (typeof message !== "object" || message === null || !("type" in message)) return;
            const typed = message as { type: string; payload?: unknown; message?: unknown };
            if (typed.type === "state" && typed.payload) setSnapshot(typed.payload as Snapshot);
            if (typed.type === "error") {
              setToast(String(typed.message ?? "Action failed"));
              window.setTimeout(() => setToast(""), 3600);
            }
          };
          socket.onclose = () => {
            if (disposed) return;
            setStage("connecting");
            reconnectTimer = window.setTimeout(openSocket, 1600);
          };
        };
        openSocket();
      } catch (error) {
        if (disposed) return;
        const message = errorMessage(error);
        setFatalError(
          message === "DISCORD_TIMEOUT"
            ? translate(chooseLocale(navigator.language), "connection.discordOnly")
            : message,
        );
        setStage("error");
      }
    }

    void boot();
    return () => {
      disposed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [attempt]);

  const send = useCallback((type: string, payload: Record<string, unknown> = {}) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setToast(translate(locale, "connection.connecting"));
      return;
    }
    const command: SocketCommand = { type, request_id: crypto.randomUUID(), payload };
    socket.send(JSON.stringify(command));
  }, [locale]);

  const sendAction = useCallback((actionId: string, targetPlayerIds: string[] = []) => {
    if (!snapshot?.game) return;
    send("submit_action", {
      action_id: actionId,
      target_player_ids: targetPlayerIds,
      expected_revision: snapshot.game.revision,
    });
  }, [send, snapshot]);

  const phase = snapshot?.game?.phase;
  const content = useMemo(() => {
    if (!snapshot) return null;
    if (!snapshot.game) return <LobbyScreen snapshot={snapshot} locale={locale} send={send} />;
    if (phase === "starting") return <RoleReveal snapshot={snapshot} locale={locale} send={send} />;
    return (
      <GameBoard
        key={`${snapshot.game.game_id}-${snapshot.game.phase}-${snapshot.game.round_number}`}
        snapshot={snapshot}
        locale={locale}
        sendAction={sendAction}
      />
    );
  }, [locale, phase, send, sendAction, snapshot]);

  return (
    <div className="app-shell">
      <div className="ambient-lines" aria-hidden="true"><span /><span /><span /></div>
      <BrandHeader locale={locale} connection={stage} onOpenGuide={() => setGuideOpen(true)} />
      <LocaleSelect locale={locale} onChange={setLocale} />

      {!snapshot && stage === "connecting" && (
        <main className="connection-screen">
          <MoonMark />
          <span className="loading-rune" />
          <h1>{translate(locale, "brand.title")}</h1>
          <p>{translate(locale, "connection.connecting")}</p>
        </main>
      )}

      {!snapshot && stage === "error" && (
        <main className="connection-screen connection-screen--error">
          <MoonMark />
          <span className="eyebrow">{translate(locale, "connection.failed")}</span>
          <h1>{translate(locale, "brand.title")}</h1>
          <p>{fatalError}</p>
          <button
            type="button"
            className="button button--danger"
            onClick={() => {
              setStage("connecting");
              setFatalError("");
              setAttempt((value) => value + 1);
            }}
          >
            {translate(locale, "connection.retry")}
          </button>
        </main>
      )}

      {content}
      {guideOpen && (
        <GameGuide
          locale={locale}
          boardOptions={snapshot?.room.board_options ?? []}
          onClose={() => setGuideOpen(false)}
        />
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
