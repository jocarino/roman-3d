// The launch countdown. The only ticking thing on the page.
//
// It counts to a commitment date, not to a scheduled launch time, and the
// reveal says so. Without JavaScript the server-rendered sentence stays put,
// which is why this only ever replaces the contents of the live region.

export class Countdown {
  constructor({ mission, root }) {
    this.mission = mission;
    this.node = root.querySelector('#countdown-value');
    this.target = new Date(mission.launch.target_utc).getTime();
    this.timer = null;
    // A bad date would otherwise replace the correct server-rendered sentence
    // with NaNd NaNh NaNm NaNs and never stop.
    if (this.node && Number.isFinite(this.target)) this.start();
  }

  start() {
    this.tick();
    // One second is enough: this clock is measured in years.
    this.timer = window.setInterval(() => this.tick(), 1000);
  }

  stop() {
    if (this.timer) window.clearInterval(this.timer);
    this.timer = null;
  }

  tick() {
    const remaining = this.target - Date.now();
    if (remaining <= 0) {
      this.node.textContent = this.mission.launch.after || this.mission.launch.display;
      this.stop();
      return;
    }
    const seconds = Math.floor(remaining / 1000);
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    this.node.textContent =
      `${days}d ${pad(hours)}h ${pad(minutes)}m ${pad(secs)}s`;
  }
}

function pad(value) {
  return String(value).padStart(2, '0');
}
