"use client";

import { useEffect, useState } from "react";
import { Users, Plus, Trash2, Pencil, Shield, Check, X, ShieldAlert, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, Chip, Modal, PageHeader, useToast } from "@/components/ui";

type User = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  permitted_repos: string[];
};

type Repo = {
  id: string;
  full_name: string;
};

export default function UsersAdminPage() {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  
  // Form fields
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("member");
  const [isActive, setIsActive] = useState(true);
  const [password, setPassword] = useState("");
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const usersList = await api.admin.users.list();
      const reposList = await api.repos.list();
      setUsers(usersList);
      setRepos(reposList);
    } catch (e) {
      toast({ kind: "error", msg: `Failed to load users: ${e}` });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function handleAddClick() {
    setEditingUser(null);
    setEmail("");
    setName("");
    setRole("member");
    setIsActive(true);
    setPassword("");
    setSelectedRepos([]);
    setModalOpen(true);
  }

  function handleEditClick(u: User) {
    setEditingUser(u);
    setEmail(u.email);
    setName(u.display_name || "");
    setRole(u.role);
    setIsActive(u.is_active);
    setPassword("");
    setSelectedRepos(u.permitted_repos);
    setModalOpen(true);
  }

  async function handleDelete(u: User) {
    if (!confirm(`Are you sure you want to delete user ${u.email}?`)) return;
    try {
      await api.admin.users.delete(u.id);
      toast({ kind: "success", msg: "User deleted successfully" });
      loadData();
    } catch (e) {
      toast({ kind: "error", msg: `Failed to delete user: ${e}` });
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        email,
        display_name: name || null,
        role,
        is_active: isActive,
        password: password || undefined,
        permitted_repos: role === "admin" ? [] : selectedRepos,
      };

      if (editingUser) {
        await api.admin.users.update(editingUser.id, payload);
        toast({ kind: "success", msg: "User updated successfully" });
      } else {
        if (!password) {
          toast({ kind: "error", msg: "Password is required for new users" });
          setBusy(false);
          return;
        }
        await api.admin.users.create(payload);
        toast({ kind: "success", msg: "User created successfully" });
      }
      setModalOpen(false);
      loadData();
    } catch (err) {
      toast({ kind: "error", msg: `Operation failed: ${err}` });
    } finally {
      setBusy(false);
    }
  }

  function toggleRepo(repoId: string) {
    if (selectedRepos.includes(repoId)) {
      setSelectedRepos(selectedRepos.filter(id => id !== repoId));
    } else {
      setSelectedRepos([...selectedRepos, repoId]);
    }
  }

  return (
    <>
      <PageHeader
        title="User & Access Management"
        subtitle="Manage developer log-ins, administrator settings, and configure repository-level access permissions."
        actions={
          <Button onClick={handleAddClick} size="sm">
            <Plus className="h-4 w-4 mr-1.5" /> Add User
          </Button>
        }
      />

      {loading ? (
        <div className="flex h-60 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      ) : (
        <Card className="border border-border bg-panel">
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border bg-panel-2/50 text-text-3 font-semibold uppercase tracking-wider">
                    <th className="px-5 py-3">User</th>
                    <th className="px-5 py-3">Role</th>
                    <th className="px-5 py-3">Status</th>
                    <th className="px-5 py-3">Repository Access</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border text-text-1">
                  {users.map(u => (
                    <tr key={u.id} className="hover:bg-panel-2/20">
                      <td className="px-5 py-4">
                        <div className="font-semibold">{u.display_name || "No Display Name"}</div>
                        <div className="text-[10px] text-text-3 font-mono">{u.email}</div>
                      </td>
                      <td className="px-5 py-4">
                        <Chip className={u.role === "admin" ? "bg-purple-950/40 text-purple-400 border border-purple-800" : "bg-neutral-800 text-neutral-400 border border-neutral-700"}>
                          {u.role.toUpperCase()}
                        </Chip>
                      </td>
                      <td className="px-5 py-4">
                        <Chip className={u.is_active ? "bg-emerald-950/40 text-emerald-400 border border-emerald-800" : "bg-red-950/40 text-red-400 border border-red-800"}>
                          {u.is_active ? "ACTIVE" : "INACTIVE"}
                        </Chip>
                      </td>
                      <td className="px-5 py-4 max-w-xs truncate">
                        {u.role === "admin" ? (
                          <span className="text-[10px] text-purple-400 font-semibold flex items-center gap-1">
                            <Shield className="h-3 w-3" /> All Repositories (Admin)
                          </span>
                        ) : u.permitted_repos.length === 0 ? (
                          <span className="text-[10px] text-yellow-400 font-semibold flex items-center gap-1">
                            <ShieldAlert className="h-3 w-3" /> No Repositories Assigned
                          </span>
                        ) : (
                          <span className="text-[10px] text-text-2 font-mono">
                            {u.permitted_repos.length} Repositories
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="flex justify-end gap-1.5">
                          <Button size="sm" variant="secondary" onClick={() => handleEditClick(u)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" variant="danger" onClick={() => handleDelete(u)} disabled={u.email === "admin@prvet.review"}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Add / Edit User Modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingUser ? "Edit User Access" : "Create New User"}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-text-2 font-semibold">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600 font-mono disabled:opacity-50"
                placeholder="developer@prvet.review"
                required
                disabled={!!editingUser}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-text-2 font-semibold">Display Name</label>
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600"
                placeholder="Jane Doe"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-text-2 font-semibold">Role</label>
              <select
                value={role}
                onChange={e => setRole(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600"
              >
                <option value="member">Standard Member (User)</option>
                <option value="admin">System Administrator</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs text-text-2 font-semibold">
                {editingUser ? "Change Password (optional)" : "Password"}
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600 font-mono"
                placeholder={editingUser ? "Leave blank to keep current" : "••••••••"}
                required={!editingUser}
              />
            </div>
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer py-1">
              <input
                type="checkbox"
                checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
                disabled={editingUser?.email === "admin@prvet.review"}
              />
              <span className="text-xs text-text-2 font-semibold">Active Account</span>
            </label>
          </div>

          {/* Repository Permissions mapping list */}
          <div className="border-t border-border pt-3">
            <label className="mb-1.5 block text-xs text-text-2 font-semibold">Repository Access Permissions</label>
            {role === "admin" ? (
              <div className="p-4 bg-purple-950/20 border border-purple-900 rounded-lg text-xs text-purple-400 flex items-center gap-2 font-mono">
                <Shield className="h-4 w-4" /> Administrators have access to all repositories automatically.
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-panel-2/30 font-mono">
                {repos.length === 0 ? (
                  <div className="p-6 text-center text-xs text-text-3">No repositories configured yet</div>
                ) : (
                  <ul className="divide-y divide-border">
                    {repos.map(r => (
                      <li key={r.id}>
                        <label className="flex cursor-pointer items-center gap-3 px-4 py-2 text-xs hover:bg-panel-2/60">
                          <input
                            type="checkbox"
                            checked={selectedRepos.includes(r.id)}
                            onChange={() => toggleRepo(r.id)}
                          />
                          <span className="text-text-1 font-semibold">{r.full_name}</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving..." : "Save Changes"}</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
