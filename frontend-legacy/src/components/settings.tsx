import { useState, useEffect } from "react";
import { fetchUsers, updateUser, createUser, uploadUsersFromExcel } from "../api/users";
import type { UserRead } from "../api/users";
import type { BulkUploadResult } from "../api/users";


function Settings() {
  const [users, setUsers] = useState<UserRead[]>([]);
  const [confirmUser, setConfirmUser] = useState<UserRead | null>(null);
  

  const [showUpload, setShowUpload]         = useState(false);
  const [uploadFile, setUploadFile]         = useState<File | null>(null);
  const [uploadResult, setUploadResult]     = useState<BulkUploadResult | null>(null);
  const [uploadLoading, setUploadLoading]   = useState(false);


  const [loggedInUser] = useState<UserRead | null>(() => {
    const saved = localStorage.getItem("currentUser");
    return saved ? (JSON.parse(saved) as UserRead) : null; 
  });
  const isAdmin = loggedInUser?.role === "PLATFORM ADMIN";
  
  const [showNewUser, setShowNewUser] = useState(false);
  const [newEmail, setNewEmail]       = useState("");
  const [newFirstName, setFirstName] = useState("");
  const [newLastName, setLastName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole]         = useState("STRUCTURAL DESIGNER");

  const [showChangePassword, setShowChangePassword] = useState(false);
  const [changePasswordValue, setChangePasswordValue] = useState("");

  useEffect(() => {
    fetchUsers().then(setUsers).catch((err) => { console.error("Failed to load users:", err); }); 
  }, []);

  function handleBanClick(user: UserRead) {
    if (user.role === "PLATFORM ADMIN") {
      alert("That is an admin account and cannot be Banned.");
    } else {
      setConfirmUser(user);
    }
  }

  async function handleConfirmBan() {
    if (confirmUser) {
      await updateUser(confirmUser.id, { is_banned: true });
      setConfirmUser(null);
      fetchUsers().then(setUsers).catch((err) => { console.error("Failed to load users:", err); });
    }
  }

  async function handleUnban(user: UserRead) {
    await updateUser(user.id, { is_banned: false });
    fetchUsers().then(setUsers).catch((err) => { console.error("Failed to load users:", err); });
  }


  async function handleChangePassword() {
    if (!loggedInUser) return;
    try {
      await updateUser(loggedInUser.id, { password: changePasswordValue });
      setShowChangePassword(false);
      setChangePasswordValue("");
    } catch (err) {
      alert(`Failed to change password: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function handleCreateUser() {
    try {
      await createUser(newEmail, newFirstName, newLastName, newPassword, newRole);
      setShowNewUser(false);
      setNewEmail(""); setFirstName(""); setLastName(""); setNewPassword(""); setNewRole("STRUCTURAL DESIGNER");
      fetchUsers().then(setUsers).catch((err) => { console.error(err); });
    } catch (err) {
      alert(`Failed to create user: ${err instanceof Error ? err.message : String(err)}`);
    }
  }


  
  async function handleUpload() {
    if (!uploadFile) return;
    setUploadLoading(true);
    try {
      const result = await uploadUsersFromExcel(uploadFile);
      setUploadResult(result);
      fetchUsers().then(setUsers).catch(console.error);
    } catch (err) {
      alert(`Upload failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setUploadLoading(false);
    }
  }



  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold tracking-wide">Settings</h1>
        <p className="text-sm text-stone-500">Welcome, {loggedInUser?.first_name}.</p>
      </div>

      {/* Confirm ban dialog */}
      {confirmUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="text-base font-semibold text-[#302d27]">Ban this user?</h2>
            <p className="mt-2 text-sm text-stone-500">
              <span className="font-medium text-[#302d27]">{confirmUser.email}</span> will be banned
              and will no longer be able to sign in.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setConfirmUser(null)}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button
                onClick={handleConfirmBan}
                className="rounded-lg bg-[#ce1b22] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#b01820]">
                Ban user
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
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Email</label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="user@example.com"
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Name</label>
                <input
                  type="text"
                  value={newFirstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="First name"
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Last Name</label>
                <input
                  type="text"
                  value={newLastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Last name"
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min. 4 characters"
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-stone-500">Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]">
                  <option value="STRUCTURAL DESIGNER">Structural Designer</option>
                  <option value="BIM DESIGNER">BIM Designer</option>
                  <option value="PLATFORM ADMIN">Platform Admin</option>
                </select>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setShowNewUser(false)}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                Cancel
              </button>
              <button
                onClick={handleCreateUser}
                className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                Create user
              </button>
            </div>
          </div>
        </div>
      )}


      {showUpload && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
        <h2 className="text-base font-semibold text-[#302d27]">Upload users from Excel</h2>
        <p className="mt-1 text-sm text-stone-500">
          File must have columns: email, first_name, last_name, password, role
        </p>
        <input
          type="file"
          accept=".xlsx"
          className="mt-4 text-sm"
          onChange={(e) => { setUploadFile(e.target.files?.[0] ?? null); setUploadResult(null); }} />
        {uploadResult && (
          <div className="mt-4 text-sm">
            <p className="font-medium text-[#302d27]">{uploadResult.created} user(s) created.</p>
            {uploadResult.errors.length > 0 && (
              <div className="mt-2">
                <p className="font-medium text-[#ce1b22]">{uploadResult.errors.length} error(s):</p>
                <ul className="mt-1 list-disc pl-4 text-stone-500">
                  {uploadResult.errors.map((e) => (
                    <li key={e.row}>Row {e.row} ({e.email}): {e.reason}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={() => { setShowUpload(false); setUploadFile(null); setUploadResult(null); }}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
            Close
          </button>
          <button
            onClick={handleUpload}
            disabled={!uploadFile || uploadLoading}
            className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540] disabled:opacity-50">
            {uploadLoading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  )}



      {showChangePassword && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
              <h2 className="text-base font-semibold text-[#302d27]">Change password</h2>
              <div className="mt-4 flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-stone-500">New password</label>
                  <input
                    type="password"
                    value={changePasswordValue}
                    onChange={(e) => setChangePasswordValue(e.target.value)}
                    placeholder="Min. 4 characters"
                    className="rounded-lg border border-stone-300 px-3 py-2 text-sm text-[#302d27] outline-none focus:border-[#302d27]"/>
                </div>
              </div>
              <div className="mt-5 flex justify-end gap-3">
                <button
                  onClick={() => { setShowChangePassword(false); setChangePasswordValue(""); }}
                  className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
                  Cancel
                </button>
                <button
                  onClick={handleChangePassword}
                  className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                  Save
                </button>
              </div>
            </div>
          </div>
        )}



      {/* table */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col rounded-lg border border-stone-200 bg-white p-4 gap-2">
          {isAdmin && (
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-[#302d27]">Accounts</h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowNewUser(true)}
                  className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
                  New user
                </button>
                <button 
                  onClick={() => setShowUpload(true)} className="rounded-lg border  border-stone-300 px-4 py-2 text-sm font-semibold text-[#302d27] transition   hover:bg-stone-50">
                  Upload users
                </button>
              </div>
          </div>
          )}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-[#302d27]">Account Management</h2>
            <button
              onClick={() => setShowChangePassword(true)}
              className="rounded-lg bg-[#302d27] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4a4540]">
              Change Password
            </button>
          </div>
          {isAdmin && ( <p className="mt-1 text-sm text-stone-500">Manage user accounts.</p> 
          )}
          {isAdmin && (
          <table className="w-full min-w-[600px] border-collapse text-left text-sm justify-between">
            <thead>
              <tr>
                <th className="text-left text-sm font-medium text-stone-500">Email</th>
                <th className="text-left text-sm font-medium text-stone-500">Name</th>
                <th className="text-left text-sm font-medium text-stone-500">Role</th>
                <th className="text-left text-sm font-medium text-stone-500">Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td className="py-2 text-sm text-[#302d27]">{user.email}</td>
                  <td className="py-2 text-sm text-[#302d27]">{user.first_name + " " + user.last_name}</td>
                  <td className="py-2 text-sm">
                    {user.is_banned ? (
                      <span className="py-2 text-sm text-[#302d27]">Banned</span>
                    ) : (
                      <span>{user.role === "STRUCTURAL DESIGNER" ? "Structural Designer" : user.role === "BIM DESIGNER" ? "BIM Designer" : "Platform Admin"}</span>
                    )}
                  </td>
                  <td className="py-2 text-sm text-[#302d27]">
                    {user.is_banned ? (
                      <button
                        onClick={() => handleUnban(user)}
                        className="text-sm font-semibold text-stone-500 transition hover:underline">
                        Unban
                      </button>
                    ) : (
                      <button
                        onClick={() => handleBanClick(user)}
                        className="text-sm font-semibold text-[#ce1b22] transition hover:underline">
                        Ban
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
        </div>
      </div>
    </div>
  ); 
}

export default Settings;
