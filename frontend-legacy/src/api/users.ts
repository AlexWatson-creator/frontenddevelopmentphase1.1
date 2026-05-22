const API_BASE = (import.meta.env.VITE_API_BASE_URL as string) || "";

export interface UserRead {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_banned: boolean;
  created_at: string;
}

export async function loginUser(email: string, password: string): Promise<UserRead> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 403) throw new Error("banned");
  if (!res.ok) throw new Error("invalid_credentials");
  return res.json() as Promise<UserRead>;
}

export async function fetchUsers(): Promise<UserRead[]> {
  const res = await fetch(`${API_BASE}/api/users`);
  if (!res.ok) throw new Error(`Failed to load users (${res.status})`);
  return res.json() as Promise<UserRead[]>;
}

export async function updateUser(
  id: number,
  changes: { role?: string; is_banned?: boolean; password?: string }
): Promise<UserRead> {
  const res = await fetch(`${API_BASE}/api/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw new Error(`Failed to update user (${res.status})`);
  return res.json() as Promise<UserRead>;
}

export async function createUser(
  email: string,
  first_name: string,
  last_name: string,
  password: string,
  role: string
): Promise<UserRead> {
  const res = await fetch(`${API_BASE}/api/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, first_name, last_name, password, role }),
  });
  if (!res.ok) throw new Error(`Failed to create user (${res.status})`);
  return res.json() as Promise<UserRead>;
}




export interface BulkUploadError {
  row: number;
  email: string;
  reason: string;
}

export interface BulkUploadResult {
  created: number;
  errors: BulkUploadError[];
}

export async function uploadUsersFromExcel(file: File): Promise<BulkUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/users/bulk-upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  return res.json() as Promise<BulkUploadResult>;
}