import { useState, useEffect } from "react";
import { fetchUsers, updateUser, createUser, uploadUsersFromExcel, deleteUser } from "../api/users";
import type { UserRead, BulkUploadResult } from "../api/users";
import { useToast, ToastContainer } from "./Toast";
import { ConfirmDialog } from "./ConfirmDialog";

const ROLE_OPTIONS: [string, string][] = [
  ["PLATFORM ADMIN",      "Platform Admin"],
  ["STRUCTURAL DESIGNER", "Structural Designer"],
  ["BIM DEVELOPER",       "BIM Developer"],
  ["INSPECTOR",           "Inspector"],
  ["ASSOCIATE",           "Associate"],
  ["DRAFTER",             "Drafter"],
  ["PROPOSAL",            "Proposal"],
  ["RESEARCH",            "Research"],
  ["LEGAL",               "Legal"],
  ["PARTNER",             "Partner"],
];

function Settings() {
  const { toasts, addToast } = useToast();
  const [users, setUsers] = useState<UserRead[]>([]);
  const [confirmUser, setConfirmUser] = useState<UserRead | null>(null);
  const [deleteFirstConfirmUser, setDeleteFirstConfirmUser] = useState<UserRead | null>(null);
  const [deleteTargetUser, setDeleteTargetUser] = useState<UserRead | null>(null);
  const [deleteMasterPassword, setDeleteMasterPassword] = useState("");

  const [showUpload, setShowUpload]       = useState(false);
  const [uploadFile, setUploadFile]       = useState<File | null>(null);
  const [uploadResult, setUploadResult]   = useState<BulkUploadResult | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  const [loggedInUser] = useState<UserRead | null>(() => {
    const saved = localStorage.getItem("currentUser");
    return saved ? (JSON.parse(saved) as UserRead) : null;
  });
  const isAdmin = ["PLATFORM ADMIN", "PARTNER", "ASSOCIATE"].includes(loggedInUser?.role ?? "");
  const canDelete = loggedInUser?.role === "PARTNER";

  const [showNewUser, setShowNewUser] = useState(false);
  const [newEmail, setNewEmail]       = useState("");
  const [newFirstName, setFirstName]  = useState("");
  const [newLastName, setLastName]    = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole]         = useState("STRUCTURAL DESIGNER");

  const [searchQuery, setSearchQuery] = useState("");
  const filteredUsers = users.filter((user) =>
    user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.first_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.last_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    user.role.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const [showChangeRole, setShowChangeRole] = useState(false);
  const [changeRoleTargetUser, setChangeRoleTargetUser] = useState<UserRead | null>(null);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [changePasswordValue, setChangePasswordValue] = useState("");

  function reloadUsers() {
    fetchUsers().then(setUsers).catch((err) => console.error("Failed to load users:", err));
  }

  useEffect(() => { reloadUsers(); }, []);

  function handleBanClick(user: UserRead) {
    if (["PLATFORM ADMIN", "PARTNER", "ASSOCIATE"].includes(user.role)) {
      addToast("That is an admin account and cannot be banned.", "error");
    } else {
      setConfirmUser(user);
    }
  }

  async function handleConfirmBan() {
    if (!confirmUser) return;
    await updateUser(confirmUser.id, { is_banned: true });
    addToast(`${confirmUser.email} has been banned.`);
    setConfirmUser(null);
    reloadUsers();
  }

  function handleDeleteClick(user: UserRead) {
    setDeleteFirstConfirmUser(user);
  }

  function handleDeleteFirstConfirm() {
    setDeleteTargetUser(deleteFirstConfirmUser);
    setDeleteMasterPassword("");
    setDeleteFirstConfirmUser(null);
  }

  async function handleConfirmDelete() {
    if (!deleteTargetUser) return;
    try {
      await deleteUser(deleteTargetUser.id, deleteMasterPassword);
      addToast(`${deleteTargetUser.email} has been deleted.`);
      setDeleteTargetUser(null);
      setDeleteMasterPassword("");
      reloadUsers();
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Failed to delete user", "error");
    }
  }

  async function handleChangeRole() {
    if (!changeRoleTargetUser) return;
    try {
      await updateUser(changeRoleTargetUser.id, { role: newRole });
      addToast("Role updated successfully.");
      setShowChangeRole(false);
      setChangeRoleTargetUser(null);
      reloadUsers();
    } catch (err) {
      addToast(`Failed to change role: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  }

  async function handleUnban(user: UserRead) {
    await updateUser(user.id, { is_banned: false });
    addToast(`${user.email} has been unbanned.`);
    reloadUsers();
  }

  async function handleChangePassword() {
    if (!loggedInUser) return;
    try {
      await updateUser(loggedInUser.id, { password: changePasswordValue });
      addToast("Password changed successfully.");
      setShowChangePassword(false);
      setChangePasswordValue("");
    } catch (err) {
      addToast(`Failed to change password: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  }

  async function handleCreateUser() {
    try {
      await createUser(newEmail, newFirstName, newLastName, newPassword, newRole);
      addToast("User created successfully.");
      setShowNewUser(false);
      setNewEmail(""); setFirstName(""); setLastName(""); setNewPassword(""); setNewRole("STRUCTURAL DESIGNER");
      reloadUsers();
    } catch (err) {
      addToast(`Failed to create user: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  }

  async function handleUpload() {
    if (!uploadFile) return;
    setUploadLoading(true);
    try {
      const result = await uploadUsersFromExcel(uploadFile);
      setUploadResult(result);
      addToast(`${result.created} user(s) uploaded successfully.`);
      reloadUsers();
    } catch (err) {
      addToast(`Upload failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setUploadLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wide">Settings</h1>
        <p className="text-sm text-stone-500">Welcome, {loggedInUser?.first_name}.</p>
      </div>

      {confirmUser && (
        <ConfirmDialog
          title="Ban this user?"
          body={<><span className="font-medium text-[#302d27]">{confirmUser.email}</span> will be banned and will no longer be able to sign in.</>}
          confirmLabel="Ban user"
          onConfirm={handleConfirmBan}
          onCancel={() => setConfirmUser(null)}
        />
      )}

      {deleteFirstConfirmUser && (
        <ConfirmDialog
          title="Delete this user?"
          body={<><span className="font-medium text-[#302d27]">{deleteFirstConfirmUser.email}</span> will be permanently removed. This cannot be undone.</>}
          confirmLabel="Continue"
          onConfirm={handleDeleteFirstConfirm}
          onCancel={() => setDeleteFirstConfirmUser(null)}
        />
      )}

      {/* Delete user — master password dialog */}
      {deleteTargetUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Permanently delete this user?</h2>
            <p className="mt-2 text-sm text-stone-500">
              <span className="font-medium text-[#302d27]">{deleteTargetUser.email}</span> will be permanently removed and cannot be recovered.
            </p>
            <div className="mt-4 flex flex-col gap-1">
              <label className="text-xs font-medium text-stone-500">Master password</label>
              <input
                type="password"
                value={deleteMasterPassword}
                onChange={(e) => setDeleteMasterPassword(e.target.value)}
                placeholder="Enter master password"
                className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => { setDeleteTargetUser(null); setDeleteMasterPassword(""); }}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="rounded-lg bg-[#ce1b22] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#b01820]">
                Delete user
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New user dialog */}
      {showNewUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Create new user</h2>
            <div className="mt-4 flex flex-col gap-3">
              {([
                ["email",    "Email",     "email",    newEmail,     setNewEmail,    "user@example.com"],
                ["text",     "Name",      "text",     newFirstName, setFirstName,   "First name"],
                ["text",     "Last Name", "text",     newLastName,  setLastName,    "Last name"],
                ["password", "Password",  "password", newPassword,  setNewPassword, "Min. 4 characters"],
              ] as const).map(([type, label, , value, setter, placeholder]) => (
                <div key={label} className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-stone-500">{label}</label>
                  <input
                    type={type}
                    value={value}
                    onChange={(e) => setter(e.target.value)}
                    placeholder={placeholder}
                    className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
                </div>
              ))}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Role</label>
                <select value={newRole} onChange={(e) => setNewRole(e.target.value)}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]">
                  {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => setShowNewUser(false)}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button onClick={handleCreateUser}
                className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                Create user
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upload dialog */}
      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Upload users from Excel</h2>
            <p className="mt-1 text-sm text-stone-500">File must have columns: email, first_name, last_name, password, role</p>
            <input id="upload-file-input" type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { setUploadFile(e.target.files?.[0] ?? null); setUploadResult(null); }} />
            <label htmlFor="upload-file-input"
              className="mt-4 inline-block cursor-pointer text-sm text-[#302d27] hover:underline">
              {uploadFile ? uploadFile.name : "No File Chosen"}
            </label>
            {uploadResult && (
              <div className="mt-4 text-sm">
                <p className="font-medium text-[#302d27]">{uploadResult.created} user(s) created.</p>
                {uploadResult.errors.length > 0 && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-[#ce1b22]">{uploadResult.errors.length} error(s):</p>
                      <button onClick={() => setUploadResult({ ...uploadResult, errors: [] })}
                        className="text-stone-400 hover:text-[#302d27] transition" aria-label="Dismiss errors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                    <ul className="mt-1 max-h-40 overflow-y-auto list-disc pl-4 text-stone-500">
                      {uploadResult.errors.map((e) => <li key={e.row}>Row {e.row} ({e.email}): {e.reason}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => { setShowUpload(false); setUploadFile(null); setUploadResult(null); }}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Close
              </button>
              <button onClick={handleUpload} disabled={!uploadFile || uploadLoading}
                className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540] disabled:opacity-50">
                {uploadLoading ? "Uploading…" : "Upload"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Change role dialog */}
      {showChangeRole && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Change Role</h2>
            <div className="mt-4 flex flex-col gap-1">
              <label className="text-xs font-medium text-stone-500">Role</label>
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)}
                className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]">
                {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => { setShowChangeRole(false); setChangeRoleTargetUser(null); }}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button onClick={handleChangeRole}
                className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Change password dialog */}
      {showChangePassword && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Change password</h2>
            <div className="mt-4 flex flex-col gap-1">
              <label className="text-xs font-medium text-stone-500">New password</label>
              <input type="password" value={changePasswordValue}
                onChange={(e) => setChangePasswordValue(e.target.value)}
                placeholder="Min. 4 characters"
                className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => { setShowChangePassword(false); setChangePasswordValue(""); }}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button onClick={handleChangePassword}
                className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* User table */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col rounded-lg border border-stone-200 bg-white p-4 gap-2">
          {isAdmin && (
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium text-[#302d27]">Accounts</h2>
              <div className="flex gap-2">
                <button onClick={() => setShowNewUser(true)}
                  className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                  New user
                </button>
                <button onClick={() => setShowUpload(true)}
                  className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold text-[#302d27] transition hover:bg-stone-50">
                  Upload users
                </button>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-[#302d27]">Account Management</h2>
            <button onClick={() => setShowChangePassword(true)}
              className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
              Change Password
            </button>
          </div>
          {isAdmin && <p className="mt-1 text-sm text-stone-500">Manage user accounts.</p>}
          {isAdmin && (
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search users..."
              className="w-full max-w-sm rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
          )}
          {isAdmin && (
            <table className="w-full min-w-[600px] border-collapse text-left text-sm">
              <thead>
                <tr>
                  {["Email", "Name", "Role", "Action"].map((h) => (
                    <th key={h} className="text-left text-sm font-medium text-stone-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <tr key={user.id}>
                    <td className="py-2 text-sm text-[#302d27]">{user.email}</td>
                    <td className="py-2 text-sm text-[#302d27]">{user.first_name} {user.last_name}</td>
                    <td className="py-2 text-sm">
                      {user.is_banned
                        ? <span className="text-[#302d27]">Banned</span>
                        : <span>{user.role.split(" ").map((w: string) => w.charAt(0) + w.slice(1).toLowerCase()).join(" ")}</span>
                      }
                    </td>
                    <td className="py-2 text-sm text-[#302d27]">
                      <div className="flex gap-3">
                        {user.is_banned
                          ? <button onClick={() => handleUnban(user)} className="text-sm font-semibold text-stone-500 transition hover:underline">Unban</button>
                          : <button onClick={() => handleBanClick(user)} className="text-sm font-semibold text-[#ce1b22] transition hover:underline">Ban</button>
                        }
                        {canDelete && (
                          <button onClick={() => { setChangeRoleTargetUser(user); setNewRole(user.role); setShowChangeRole(true); }}
                            className="text-sm font-semibold text-stone-400 transition hover:text-[#ce1b22] hover:underline">
                            Change Role
                          </button>
                        )}
                        {canDelete && (
                          <button onClick={() => handleDeleteClick(user)}
                            className="text-sm font-semibold text-stone-400 transition hover:text-[#ce1b22] hover:underline">
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <ToastContainer toasts={toasts} />
    </div>
  );
}

export default Settings;
