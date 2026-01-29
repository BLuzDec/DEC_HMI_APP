# TwinCAT Side: ADS Setup for PC Client

Once your PC-side ADS client (this app) is working, you need to configure **TwinCAT** so it accepts connections from your PC and allows ADS read/write.

---

## 1. Add a route from TwinCAT (PLC) to your PC

ADS needs a **route** on **both** sides:

- **On the PC:** Often handled by TwinCAT Router (if TwinCAT is installed on the PC) or by pyads on Linux.
- **On the PLC / TwinCAT:** You must add a route that points to your PC.

### Option A: Using TwinCAT System Manager (on the PLC or engineering PC)

1. Open **TwinCAT 3** (or TwinCAT 2) and go to **System** → **Routes** (or **Static Routes**).
2. **Add route:**
   - **Name:** e.g. `RouteToMyPC`
   - **Address (AmsNetId) of the PC:** Use **exactly the value you enter in the app** in the **“PC IP”** field (e.g. `192.168.1.100` or `192.168.1.100.1.1`).
   - **Host / IP:** Your PC’s IP (e.g. `192.168.1.100`) — same as the PC IP you provide in the app.
3. **Important:** Disable **“Unidirectional”** (route must be bidirectional for normal ADS).
4. Save and activate the configuration.

### Option B: Add route from Python (pyads) on your PC

You can create the route on the **target (PLC)** from your PC using pyads (one-time setup):

```python
import pyads

SENDER_AMS = '192.168.0.1.1.1'   # Your PC's AmsNetId (see below)
PLC_IP = '192.168.0.2'             # PLC / CX IP
PLC_USER = ''         # Windows user on the PLC (if required)
PLC_PASSWORD = ''                  # Password (empty for local)
ROUTE_NAME = 'RouteToMyPC'
HOSTNAME = 'MyPC'                   # Your PC hostname or IP

pyads.open_port()
pyads.set_local_address(SENDER_AMS)
pyads.add_route_to_plc(SENDER_AMS, HOSTNAME, PLC_IP, PLC_USER, PLC_PASSWORD, route_name=ROUTE_NAME)
pyads.close_port()
```

Run this once (with correct IPs and user/password); then your app can connect using the PLC’s AmsNetId.

---

## 2. What you enter in the app

- **Target (PLC):** The PLC’s AmsNetId (e.g. `192.168.1.10.1.1`) — the device you connect **to**.
- **PC IP:** Your PC’s IP (e.g. `192.168.1.100`) or full AmsNetId (e.g. `192.168.1.100.1.1`). **This is the address used for the route on the PLC** — the app uses exactly what you type here as your PC’s address (for `set_local_address` / route creation).

So: the **IP address of your PC** is the one you provide in the app in the **“PC IP”** field; the app uses that value for ADS (local/sender address). The route on the PLC must point to this same address.

---

## 3. Variables for ADS: exchange_variables and recipes

Yes. For ADS you use the same **exchange_variables.csv** (and **recipe_variables.csv** if you use recipes) as for Snap7/Simulation. The app loads the variable list from these files and uses it for ADS too.

- **What to put:** In the **Variable** column put the **exact symbol names from your Beckhoff PLC** (as in TwinCAT), e.g. `GVL.Dose_number`, `MAIN.StableWeight`, `GVL.Pressure`. The app will use these names for ADS `read_by_name(...)`.
- **No extra JSON for ADS:** Snap7 uses `snap7_node_ids.json` (DB, offset, type). For ADS you don’t need a separate mapping file — the **Variable** name in the CSV **is** the symbol name. Just match the PLC.
- **Choosing what to put:** You decide which PLC variables appear in the app by listing them in the CSV. Put only the variables you want to plot or use, with the **correct names from the PLC** (same as in TwinCAT symbol table).

**exchange_variables.csv** example for ADS (same columns as for Snap7; names = PLC symbol names):

| Variable        | Type | Min | Max | Unit |
|-----------------|------|-----|-----|------|
| GVL.Dose_number | Int  | 0   | 1000| count|
| GVL.StableWeight| Real | 0   | 1000| kg   |
| MAIN.Pressure   | Real | 0   | 10  | bar  |

Use **recipe_variables.csv** the same way for recipe parameters: **Variable** = exact PLC symbol name (e.g. `GVL.Recipe_Temperature_Set`).

---

## 4. TwinCAT project (PLC side)

- **Runtime:** TwinCAT PLC Runtime must be **running** and the **configuration loaded**.
- **Symbols:** For `read_by_name` / `write_by_name` you need **symbol names** (e.g. `GVL.MyVar`). In TwinCAT:
  - Compile the PLC project.
  - Enable **“Create symbol file”** / upload symbols so the PLC has a symbol table (optional for symbol access; some setups use index/offset instead).
- **Port:** TwinCAT 3 PLC usually uses port **851** (often used as `PORT_TC3PLC1` in pyads). Your app or pyads will use this when connecting to the PLC’s AmsNetId.

---

## 5. Firewall (PLC and PC)

- **ADS uses TCP port 48898** (and optionally 48899). Allow these between your PC and the PLC/CX.
- On the **PLC (Windows CE/embedded):** If it has a firewall, allow ADS.
- On your **PC:** Allow inbound/outbound for ADS if a firewall is active.

---

## 6. Checklist

| Step | Where | Action |
|------|--------|--------|
| 1 | TwinCAT (PLC) | Add route to your PC: PC AmsNetId + PC IP/hostname, **unidirectional = off** |
| 2 | App (PC) | Use PLC AmsNetId (e.g. `192.168.1.10.1.1`) and PLC IP if required by your connection API |
| 3 | TwinCAT | PLC Runtime running, config activated |
| 4 | TwinCAT | Symbol file created if you use symbol names |
| 5 | Network | Firewall allows ADS (e.g. 48898) between PC and PLC |

After this, your PC ADS client can connect to the PLC’s AmsNetId and read/write variables by name (or by index/offset if you use that in your app).

---

## 7. Troubleshooting: "Target machine not found - Missing ADS routes (7)"

This error means **your PC does not have an ADS route to the PLC**. The app (client) runs on the PC and tries to reach the PLC (target); the route must exist **on the PC**.

### Fix: Add the route on your PC

**Option A – TwinCAT 3 Runtime or XAE on your PC**

**Exact steps (TwinCAT 3 Runtime):**

1. **Open TwinCAT**  
   - **System tray:** Right‑click the **TwinCAT** icon (green/blue) in the taskbar → **Show TwinCAT** (or **TwinCAT 3**).  
   - Or **Start menu** → **Beckhoff** → **TwinCAT 3** → **TwinCAT 3 XAE** or **TwinCAT 3 Runtime**.
2. **Open Routes**  
   - In the TwinCAT window: **System** → **Routes** (or **Static Routes**).  
   - Or in the left tree: expand **System** → click **Routes**.
3. **Add a route**  
   - Click **Add** or **Add Route** (or right‑click in the route list → **Add**).  
   - **AmsNetId (target):** Enter exactly what you use as **Target (PLC)** in the app, e.g. `192.168.0.2.1.1` (or `192.168.0.2` if your router expects that).  
   - **Address / IP / Host:** Enter the **IPC/PLC IP** only, e.g. `192.168.0.2`.  
   - **Name:** Optional, e.g. `RouteToIPC`.  
4. **Save / Activate**  
   - Confirm or save the configuration so the route is active.

**If you don’t see “Routes”:** You may have only the Runtime panel. Try: **TwinCAT** system tray icon → **Show** → look for **Routes** or **Configuration**. In some Runtime installs, routes are under **TwinCAT 3** → **Configuration** or via a separate “TwinCAT Router” / “Route Manager” entry in the Start menu.

**Option B – "Add Route" dialog (TwinCAT)**

1. In TwinCAT, use **Add Route** (or **Add Route to Remote System**).
2. Enter the **PLC AmsNetId** (e.g. `192.168.0.2.1.1`) and the **PLC IP** (e.g. `192.168.0.2`).
3. If asked for **Local AmsNetId**, use your PC (e.g. `192.168.0.102.1.1` or leave default).

**Option C – TwinCAT not on PC**

- On Windows, pyads uses the **TwinCAT Router**; the route is managed by TwinCAT. Install **TwinCAT 3 Runtime** on the PC and add the route as above.

### Quick checks

| Check | What to do |
|--------|------------|
| PLC reachable? | From the PC: `ping 192.168.0.2` (use your PLC IP). |
| Same subnet? | PC and PLC must be on the same subnet (e.g. 192.168.0.x). |
| Target (PLC) in app | Must be PLC AmsNetId, e.g. `192.168.0.2` or `192.168.0.2.1.1`. |
| Route on PC | Route on the **PC** must map PLC AmsNetId to PLC IP. |

Once the route exists on the PC, restart the app and connect again; "Target machine not found" should disappear.

---

## 8. PC without TwinCAT – only Ethernet to the IPC

If your computer **does not have TwinCAT** and the only link to the TwinCAT IPC is an **Ethernet cable**, ADS still needs the TwinCAT stack on your PC. On Windows there is no way to use ADS (pyads) without it.

### What you need on your PC

1. **TwinCAT 3 Runtime** (not the full development environment)
   - This is a **free** Beckhoff package that provides the **TwinCAT Router** and ADS stack.
   - Download from [Beckhoff Download](https://www.beckhoff.com/download) → TwinCAT 3 → Runtime.
   - Install it on your PC. You do **not** need TwinCAT XAE (engineering); the Runtime is enough for the app to talk ADS to the IPC.

2. **Network**
   - Connect your PC to the IPC with the Ethernet cable.
   - Set your **PC** to a **static IP** on the same subnet as the IPC (e.g. PC `192.168.0.102`, IPC `192.168.0.2`).
   - Ensure you can **ping** the IPC from the PC (`ping 192.168.0.2`).

3. **Route on your PC**
   - After installing TwinCAT 3 Runtime, open the TwinCAT route configuration (e.g. from the system tray icon or **TwinCAT 3** → **System** → **Routes**).
   - **Add route** to the IPC:
     - **AmsNetId (target):** IPC AmsNetId, e.g. `192.168.0.2.1.1` (same as **Target (PLC)** in the app).
     - **Address / IP:** IPC IP, e.g. `192.168.0.2`.

4. **Route on the IPC (one-time)**
   - The IPC must also know how to reach your PC. That route is configured **on the IPC** (or from any machine that has TwinCAT and can reach the IPC).
   - If you have **TwinCAT on the IPC** (e.g. via remote desktop or local access): add a route there with **AmsNetId** = your PC (e.g. `192.168.0.102.1.1`) and **Host** = your PC IP (`192.168.0.102`).
   - If the IPC was set up by someone else, ask them to add this route to your PC’s IP/AmsNetId.

### Summary

| Where        | What |
|-------------|------|
| Your PC     | Install **TwinCAT 3 Runtime** (free). Set static IP. Add route: IPC AmsNetId → IPC IP. |
| IPC (TwinCAT)| Add route: PC AmsNetId → PC IP (once). |
| App         | **Target (PLC)** = IPC AmsNetId (e.g. `192.168.0.2.1.1`). **PC IP** = your PC IP (e.g. `192.168.0.102`). |

After that, your PC has the ADS router and a route to the IPC; the IPC knows your PC. The app can then connect over Ethernet using ADS.
