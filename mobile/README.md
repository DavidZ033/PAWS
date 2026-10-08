# PAWS phone app

A React Native app (built with Expo) for controlling the robot over home WiFi.

The focus is the code that talks to the robot. The screens are deliberately plain and are meant as a base to build on.

## Run it

1. Install [Node.js](https://nodejs.org) 20 or newer.
2. Install the **Expo Go** app on your phone (App Store or Google Play).
3. In this folder:

   ```bash
   npm install
   npx expo start
   ```

4. Scan the QR code with your phone.
5. On the **Settings** tab, enter the robot's IP address and tap **Save and connect**.

No robot handy? Start the simulator on your computer (`python -m paws serve` in the repository root) and enter your computer's IP address instead. You can also run the app in a browser with `npx expo start --web` and use `localhost`.

## How the code is organised

```
App.tsx                     tab bar and app shell
src/
  api/
    types.ts                shapes of every message to and from the robot
    client.ts               PawsClient: REST calls (feed, schedule, events, navigation)
    socket.ts               PawsSocket: live status, events and low-delay driving
  state/
    RobotContext.tsx        one shared connection and status for all screens
  components/
    Joystick.tsx            touch joystick
    CameraView.tsx          live video (web view on phones)
    CameraView.web.tsx      live video (plain img tag in a browser)
    ui.tsx                  button, card, row
  screens/
    ControlScreen.tsx       video, joysticks, feed, launch, stop
    ScheduleScreen.tsx      feeding times
    EventsScreen.tsx        history with snapshots
    SettingsScreen.tsx      robot address and options
```

### The two ways the app talks to the robot

**`PawsClient` (REST)** is for things you do once: feed now, add a schedule entry, load events. Every method returns a promise and throws an `ApiError` with a readable message on failure.

```ts
const client = new PawsClient({ host: '192.168.1.50', port: 8000, token: '' });
await client.feed(2);
await client.addSchedule({ time: '08:00', portions: 1, days: [], label: 'Breakfast', enabled: true });
await client.goto({ x: 1, y: 0.5 });
```

**`PawsSocket` (WebSocket)** is for anything live. It receives the robot's status five times a second and new events as they happen, and it sends drive commands with very little delay.

```ts
const socket = new PawsSocket(socketUrl(settings), {
  onStatus: (status) => console.log(status.pose),
  onEvent: (event) => console.log(event.message),
});
socket.connect();
socket.setDrive({ vx: 0.5 });   // forward at half speed
socket.setDrive({ vx: 0 });     // stop
```

While any drive value is non-zero the socket re-sends it ten times a second. The robot stops on its own if those messages stop arriving, so closing the app or losing WiFi cannot leave it driving. The socket also reconnects by itself.

### Drive directions

The robot's convention is: `vx` forward, `vy` **left**, `omega` **counter-clockwise**. A joystick pushed right is therefore a negative `vy`, and turning right is a negative `omega`. `ControlScreen.tsx` does that flip in one place.

## Building a standalone app

Expo Go is enough for development. For an installable build, see the Expo docs for `eas build`. `app.json` already contains the two settings a standalone build needs to talk to a robot over plain HTTP on the local network (`usesCleartextTraffic` on Android and `NSAllowsLocalNetworking` on iOS).

## Checks

```bash
npm run typecheck
```
