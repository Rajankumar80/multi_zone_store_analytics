import cv2
import numpy as np
import json
import time
import threading


class ZoneManager:
    """
    Manages all zone state: entry/exit hysteresis, dwell timing, event logging.

    Design decisions
    ----------------
    - All zone logic runs on the main thread — no locking needed for zone state.
    - cumulative_dwell is shared with the dwell writer thread and is protected
      by _dwell_lock.
    - Dwell file is written on a daemon thread — the main loop never blocks on disk.
    - streak dicts are cleaned up immediately on entry/exit so they never grow.
    - cumulative_dwell is capped at 500 entries so memory stays bounded.
    - dwell_secs is clamped to >= 0 to guard against NTP clock adjustments.
    """

    _MAX_DWELL_ENTRIES = 500   # maximum unique tracker IDs kept in memory

    def __init__(self, camera_data, entry_frames=4, exit_frames=6,
                 dwell_file="zone_dwell_summary.json"):
        self.ENTRY_FRAMES = entry_frames
        self.EXIT_FRAMES  = exit_frames
        self.DWELL_FILE   = dwell_file

        # Homography (optional — None means pixel-space zone tests only)
        self.homography = (
            np.array(camera_data["homography"], dtype=np.float32)
            if camera_data.get("homography") is not None
            else None
        )

        # Zone geometry
        self.zones_pixel = {k: v["pts"] for k, v in camera_data["zones"].items()}
        # self.zones_world = {k: v["world"] for k, v in camera_data["zones"].items()}
        self.zones_world = {}
        for name, pts in self.zones_pixel.items():
            world_pts = []
            for p in pts:
                wp = self.pixel_to_world(p[0], p[1])
                # If homography is valid, use the world point; otherwise, fallback to pixel
                world_pts.append(wp if wp is not None else p)
            self.zones_world[name] = world_pts

        # Per-zone state (main thread only — no lock needed)
        self.confirmed_inside = {name: set() for name in self.zones_pixel}
        self.inside_streak    = {}   # (tid, zone) → consecutive inside-frame count
        self.outside_streak   = {}   # (tid, zone) → consecutive outside-frame count
        self.zone_entry_count = {name: 0 for name in self.zones_pixel}
        self.zone_exit_count  = {name: 0 for name in self.zones_pixel}
        self.entry_epoch      = {}   # (tid, zone) → entry timestamp

        # Dwell accumulator — shared with dwell writer thread, protected by lock
        self.cumulative_dwell = {}   # tid → {zone: total_seconds}
        self._dwell_lock       = threading.Lock()
        self._dwell_dirty      = False
        self._last_dwell_flush = 0.0
        self._DWELL_INTERVAL   = 10.0   # minimum seconds between file writes

        threading.Thread(target=self._dwell_writer_loop, daemon=True).start()

    # ── Formatting helpers ────────────────────────────────────────────────────

    @staticmethod
    def fmt_ts(epoch):
        return time.strftime("%H:%M:%S", time.localtime(epoch))

    @staticmethod
    def fmt_duration(secs):
        secs = int(secs)
        m, s = divmod(secs, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"

    # ── Coordinate transform ──────────────────────────────────────────────────

    def pixel_to_world(self, x, y):
        """Convert pixel foot-point to world (metric) coordinates, or None."""
        if self.homography is None:
            return None
        pt = np.array([[[float(x), float(y)]]], dtype=np.float32)
        return cv2.perspectiveTransform(pt, self.homography)[0][0]

    # ── Hysteresis ────────────────────────────────────────────────────────────

    def apply_hysteresis(self, tid, zone, raw_inside, now, event_log):
        """
        Debounce raw point-in-polygon results.
        Requires ENTRY_FRAMES consecutive inside frames to confirm entry,
        and EXIT_FRAMES consecutive outside frames to confirm exit.
        """
        key          = (tid, zone)
        confirmed_in = tid in self.confirmed_inside[zone]

        if raw_inside:
            self.outside_streak[key] = 0
            if not confirmed_in:
                self.inside_streak[key] = self.inside_streak.get(key, 0) + 1
                if self.inside_streak[key] >= self.ENTRY_FRAMES:
                    self.confirmed_inside[zone].add(tid)
                    # Entry confirmed — streak key no longer needed
                    self.inside_streak.pop(key, None)
                    self.zone_entry_count[zone] += 1
                    self.entry_epoch[key] = now
                    event_log.append({
                        "event":       "ENTRY",
                        "id":          int(tid),
                        "zone":        zone,
                        "entry_time":  self.fmt_ts(now),
                        "entry_epoch": round(now, 3),
                    })
                    
            else:
                self.inside_streak[key] = 0
        else:
            self.inside_streak[key] = 0
            if confirmed_in:
                self.outside_streak[key] = self.outside_streak.get(key, 0) + 1
                if self.outside_streak[key] >= self.EXIT_FRAMES:
                    self.process_exit(tid, zone, now, event_log)
            else:
                self.outside_streak[key] = 0

    # ── Exit processing ───────────────────────────────────────────────────────

    def process_exit(self, tid, zone, now, event_log, reason=None):
        """
        Finalise a zone exit: compute dwell, update totals, emit event.
        Safe to call even if the person is not currently confirmed inside
        (guard at top prevents double-processing).
        """
        if tid not in self.confirmed_inside[zone]:
            return

        key = (tid, zone)
        self.confirmed_inside[zone].discard(tid)
        # Exit confirmed — streak key no longer needed
        self.outside_streak.pop(key, None)
        self.zone_exit_count[zone] += 1

        entry_ep = self.entry_epoch.pop(key, now)
        # max(0.0) guards against NTP clock skew making dwell appear negative
        dwell_secs = max(0.0, round(now - entry_ep, 1))

        with self._dwell_lock:
            if tid not in self.cumulative_dwell:
                self.cumulative_dwell[tid] = {}
            prev  = self.cumulative_dwell[tid].get(zone, 0.0)
            total = round(prev + dwell_secs, 1)
            self.cumulative_dwell[tid][zone] = total
            self._dwell_dirty = True   # set inside same lock — one atomic update

        evt = {
            "event":            "EXIT",
            "id":               int(tid),
            "zone":             zone,
            "entry_time":       self.fmt_ts(entry_ep),
            "exit_time":        self.fmt_ts(now),
            "entry_epoch":      round(entry_ep, 3),
            "exit_epoch":       round(now, 3),
            "dwell_secs":       dwell_secs,
            "dwell_formatted":  self.fmt_duration(dwell_secs),
            "total_dwell_secs": total,
            "total_dwell_fmt":  self.fmt_duration(total),
        }
        if reason:
            evt["reason"] = reason
        event_log.append(evt)
        

    # ── Lost-track cleanup ────────────────────────────────────────────────────

    def cleanup_lost_tracks(self, active_ids, now, event_log):
        """
        Force-exit every person whose tracker ID is no longer in active_ids.
        Called once per frame after YOLO tracking.
        """
        all_confirmed = set().union(*self.confirmed_inside.values())
        for tid in (all_confirmed - active_ids):
            for zone in self.zones_pixel:
                if tid in self.confirmed_inside[zone]:
                    self.process_exit(tid, zone, now, event_log, reason="track_lost")
            # Clean up any residual streak entries for this lost track
            for zone in self.zones_pixel:
                self.inside_streak.pop((tid, zone),  None)
                self.outside_streak.pop((tid, zone), None)

    # ── Background dwell writer ───────────────────────────────────────────────

    def _dwell_writer_loop(self):
        """
        Daemon thread: writes dwell_summary.json at most every _DWELL_INTERVAL
        seconds, and only when data has changed.

        Dirty flag is reset AFTER a successful write so that a failed write
        (disk full, permission error) is automatically retried on the next cycle.
        """
        while True:
            time.sleep(1.0)

            # Check under lock — fast, just reading two booleans
            with self._dwell_lock:
                dirty = self._dwell_dirty
                since = time.time() - self._last_dwell_flush

            if not (dirty and since >= self._DWELL_INTERVAL):
                continue

            # Take snapshot and trim oversized dict — all under one lock acquisition
            with self._dwell_lock:
                # Cap memory: keep only the most recent _MAX_DWELL_ENTRIES tids.
                # Older data is already persisted to disk.
                if len(self.cumulative_dwell) > self._MAX_DWELL_ENTRIES:
                    oldest = list(self.cumulative_dwell.keys())[:-self._MAX_DWELL_ENTRIES]
                    for k in oldest:
                        del self.cumulative_dwell[k]
                snapshot = {tid: dict(z) for tid, z in self.cumulative_dwell.items()}

            # Build summary outside the lock — no need to hold it during formatting
            summary = {
                f"id_{tid}": {
                    zone: {"total_secs": s, "total_fmt": self.fmt_duration(s)}
                    for zone, s in zones.items()
                }
                for tid, zones in snapshot.items()
            }

            try:
                with open(self.DWELL_FILE, "w") as f:
                    json.dump(summary, f, indent=2)
                # Reset dirty flag ONLY after a successful write.
                # If write fails, dirty stays True so the next check retries.
                with self._dwell_lock:
                    self._dwell_dirty      = False
                    self._last_dwell_flush = time.time()
            except Exception as e:
                print(f"[WARN] dwell write failed — will retry: {e}")
