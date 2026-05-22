

const DEMO_EMAIL: string[] = ["demo@jablonsky.ca","demo2@jablonsky.ca","demo3@jablonsky.ca","demo4@jablonsky.ca"];
const DEMO_PASSWORD: string[] = ["demo1","demo2","demo3","demo4"];

export type DemoCred = {
  email: string;
  name: string;
  role: string;
  password: string;
}

export const Demo_Credentials: DemoCred[] = [
  { email: DEMO_EMAIL[0], name: "Demo User", role: "Admin", password: DEMO_PASSWORD[0] },
  { email: DEMO_EMAIL[1], name: "Demo User 2", role: "User", password: DEMO_PASSWORD[1] },
  { email: DEMO_EMAIL[2], name: "Demo User 3", role: "Admin", password: DEMO_PASSWORD[2] },
  { email: DEMO_EMAIL[3], name: "Demo User 4", role: "User", password: DEMO_PASSWORD[3] },
];