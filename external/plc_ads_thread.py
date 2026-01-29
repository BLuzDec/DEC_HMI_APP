"""
ADS / EtherCAT communication thread for Beckhoff PLCs.

Uses pyads to connect to TwinCAT PLCs, set local (PC) address for the route,
and read variables by symbol name. Variable list comes from the app's
exchange/recipe CSVs.
"""

import time
import logging
import threading
import sys

try:
    import pyads
    PYADS_AVAILABLE = True
except ImportError:
    PYADS_AVAILABLE = False
    pyads = None


def _to_ams_netid(address):
    """Convert IP (a.b.c.d) to AmsNetId (a.b.c.d.1.1) if needed."""
    if not address or not address.strip():
        return address
    parts = address.strip().split(".")
    if len(parts) == 4:
        return f"{address.strip()}.1.1"
    return address.strip()


class PLCADSThread(threading.Thread):
    """Thread for ADS/EtherCAT communication with Beckhoff PLCs."""

    def __init__(self, address, signal_emitter, status_emitter=None, comm_speed=0.05,
                 local_address=None, variable_names=None):
        super().__init__()
        self.address = address
        self.local_address = local_address
        self.signal_emitter = signal_emitter
        self.status_emitter = status_emitter
        self.comm_speed = comm_speed
        self.variable_names = variable_names or []
        self.stop_event = threading.Event()
        self._comm_speed_lock = threading.Lock()
        self.read_count = 0
        self.error_count = 0
        self.last_error = None
        self._last_success_read_time = None
        self._last_interval_ms = None
        self._last_read_error = None  # Show in UI when a symbol read fails
        self._plc = None

    def _emit_status(self, status_type, message, details=None):
        if self.status_emitter:
            self.status_emitter.emit(status_type, message, details or {})

    def run(self):
        if not PYADS_AVAILABLE:
            self._emit_status("error", "pyads is not installed. Install with: pip install pyads",
                             {"error_count": self.error_count})
            self._emit_status("disconnected", "Connection failed")
            return

        self._emit_status("info", f"Connecting to Beckhoff PLC (ADS) at {self.address} (PC: {self.local_address or 'default'})...")

        ams_netid = _to_ams_netid(self.address)
        try:
            pyads.open_port()
            # SetLocalAddress is only for Linux; on Windows the TwinCAT Router manages the local address
            if self.local_address and sys.platform != "win32":
                local_ams = _to_ams_netid(self.local_address)
                pyads.set_local_address(local_ams)
            self._plc = pyads.Connection(ams_netid, pyads.PORT_TC3PLC1)
            self._plc.open()
            self._emit_status("connected", f"ADS connected to {self.address} (PC: {self.local_address or '—'})")
        except Exception as e:
            logging.error(f"ADS connection failed: {e}")
            self._emit_status("error", str(e), {"error_count": self.error_count})
            self._emit_status("disconnected", "Connection failed")
            try:
                pyads.close_port()
            except Exception:
                pass
            return

        while not self.stop_event.is_set():
            try:
                now = time.time()
                if self._last_success_read_time is not None:
                    self._last_interval_ms = (now - self._last_success_read_time) * 1000
                self._last_success_read_time = now

                self._last_read_error = None  # Clear only when we start a new cycle
                for var_name in self.variable_names:
                    if self.stop_event.is_set():
                        break
                    try:
                        raw = self._plc.read_by_name(var_name)
                        # Convert to native Python types so main thread and graphs handle values correctly
                        if isinstance(raw, bool):
                            value = int(raw)
                        elif isinstance(raw, (list, tuple)):
                            value = [float(x) if isinstance(x, (int, float)) else x for x in raw]
                        elif raw is not None:
                            try:
                                value = float(raw)  # int, float, numpy scalars
                            except (ValueError, TypeError):
                                value = raw
                        else:
                            value = raw
                        if self.signal_emitter:
                            self.signal_emitter.emit(var_name, value)
                    except Exception as e:
                        err_msg = f"{var_name}: {e}"
                        self._last_read_error = err_msg
                        logging.warning("ADS read_by_name failed: %s", err_msg)
                        if self.status_emitter:
                            self.status_emitter.emit("info", f"Read failed: {err_msg}", {})

                self.read_count += 1
                if self.read_count % 100 == 0:
                    details = {
                        "read_count": self.read_count,
                        "error_count": self.error_count,
                        "last_interval_ms": self._last_interval_ms,
                        "requested_interval_ms": self.comm_speed * 1000,
                    }
                    if self._last_read_error:
                        details["read_error"] = self._last_read_error
                    self._emit_status("stats", "Communication active", details)

                with self._comm_speed_lock:
                    current_speed = self.comm_speed
                time.sleep(current_speed)

            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                logging.error("ADS communication error: %s", e)
                self._emit_status("error", str(e), {"error_count": self.error_count})
                time.sleep(5)

        try:
            if self._plc:
                self._plc.close()
        except Exception:
            pass
        try:
            pyads.close_port()
        except Exception:
            pass
        self._emit_status("disconnected", "ADS communication stopped.")

    def update_speed(self, new_speed):
        if new_speed > 0:
            with self._comm_speed_lock:
                self.comm_speed = new_speed

    def stop(self):
        self.stop_event.set()
