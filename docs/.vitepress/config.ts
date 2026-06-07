import { defineConfig } from "vitepress";

export default defineConfig({
  title: "Basketball IQ Docs",
  description: "User and Technical Manuals for the Basketball IQ Analytics Platform",
  base: "/",
  themeConfig: {
    nav: [
      { text: "User Manual", link: "/user-manual/README" },
      { text: "Technical Manual", link: "/technical/README" },
    ],
    sidebar: {
      "/user-manual/": [
        {
          text: "User Manual",
          items: [
            { text: "Home", link: "/user-manual/README" },
            { text: "Quickstart", link: "/user-manual/00-quickstart" },
            { text: "Login & Account", link: "/user-manual/01-login-and-account" },
            { text: "Dashboard", link: "/user-manual/02-dashboard" },
            { text: "Scouting Reports", link: "/user-manual/03-scouting-reports" },
            { text: "Game Day & Simulation", link: "/user-manual/04-game-day-simulation" },
            { text: "Game Tracker (Live)", link: "/user-manual/05-game-tracker-live" },
            { text: "Event Heatmap", link: "/user-manual/06-event-heatmap" },
            { text: "Play Builder", link: "/user-manual/07-play-builder" },
            { text: "Video Analysis", link: "/user-manual/08-video-analysis" },
            { text: "Training & Pose", link: "/user-manual/09-training-pose" },
            { text: "Matchup Workspace", link: "/user-manual/10-matchup-workspace" },
            { text: "Admin", link: "/user-manual/11-admin" },
            { text: "Coach Mode", link: "/user-manual/12-coach-mode" },
            {
              text: "Scenarios",
              items: [
                { text: "Weekly Prep", link: "/user-manual/scenarios/01-weekly-prep" },
                { text: "Live Game Night", link: "/user-manual/scenarios/02-live-game-night" },
                { text: "Post-Game Review", link: "/user-manual/scenarios/03-post-game-review" },
                { text: "Training: Shooting Form", link: "/user-manual/scenarios/04-training-shooting-form" },
              ],
            },
            { text: "Glossary", link: "/user-manual/glossary" },
            { text: "FAQ", link: "/user-manual/faq" },
          ],
        },
      ],
      "/technical/": [
        {
          text: "Technical Manual",
          items: [
            { text: "Home", link: "/technical/README" },
            { text: "Architecture", link: "/technical/01-architecture" },
            { text: "Data Model", link: "/technical/02-data-model" },
            { text: "API Reference", link: "/technical/03-api-reference" },
            { text: "Deployment", link: "/technical/04-deployment" },
            { text: "Local Dev", link: "/technical/05-local-dev" },
            { text: "CV Engine", link: "/technical/06-cv-engine" },
            { text: "Workers", link: "/technical/07-workers" },
            { text: "LLM Integration", link: "/technical/08-llm-integration" },
            { text: "Security", link: "/technical/09-security" },
            { text: "Monitoring", link: "/technical/10-monitoring" },
            { text: "Troubleshooting", link: "/technical/11-troubleshooting" },
            { text: "Runbooks", link: "/technical/12-runbooks" },
            { text: "Extending", link: "/technical/13-extending" },
          ],
        },
      ],
    },
    socialLinks: [
      { icon: "github", link: "https://github.com/your-org/basketball-iq" },
    ],
  },
});
