"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Users, Trash2, Edit, Plus, X, Search } from "lucide-react";

export default function FacesPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<any>(null);
  const [form, setForm] = useState({ name: "", email: "", role: "user", file: null as File | null });
  const [submitting, setSubmitting] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/users");
      const data = await res.json();
      setUsers(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const filteredUsers = users.filter((u) =>
    u.name?.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async (userId: number, userName: string) => {
    if (!confirm(`Delete "${userName}"? This action cannot be undone.`)) return;
    try {
      const res = await fetch(`http://localhost:8000/api/users/${userId}`, { method: "DELETE" });
      const data = await res.json();
      if (data.status === "success") {
        fetchUsers();
      } else {
        alert("Delete failed: " + data.message);
      }
    } catch (e) {
      console.error(e);
      alert("Delete failed");
    }
  };

  const openEdit = (user: any) => {
    setEditingUser(user);
    setForm({ name: user.name, email: user.email, role: user.role, file: null });
    setShowModal(true);
  };

  const openAdd = () => {
    setEditingUser(null);
    setForm({ name: "", email: "", role: "user", file: null });
    setShowModal(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.email) {
      alert("Name and email are required.");
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("name", form.name);
      formData.append("email", form.email);
      formData.append("role", form.role);

      if (editingUser) {
        if (form.file) formData.append("photo", form.file);
        const res = await fetch(`http://localhost:8000/api/users/${editingUser.id}`, {
          method: "PUT",
          body: formData,
        });
        const data = await res.json();
        if (data.status === "success") {
          setShowModal(false);
          fetchUsers();
        } else {
          alert("Update failed: " + data.message);
        }
      } else {
        if (!form.file) { alert("Photo is required for new registration."); return; }
        formData.append("photo", form.file);
        const res = await fetch("http://localhost:8000/api/users/register", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (data.status === "success") {
          setShowModal(false);
          fetchUsers();
        } else {
          alert("Registration failed: " + data.message);
        }
      }
    } catch (e) {
      console.error(e);
      alert("Operation failed");
    } finally {
      setSubmitting(false);
    }
  };

  const getPhotoUrl = (photo: string) => {
    if (!photo) return "https://i.pravatar.cc/150?u=unknown";
    return photo.startsWith("http") ? photo : `http://localhost:8000/${photo.replace(/\\/g, "/")}`;
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-50 p-6 md:p-12 font-sans selection:bg-indigo-500/30">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-neutral-800">
          <div>
            <div className="flex items-center gap-3">
              <a href="/" className="text-neutral-400 hover:text-white transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </a>
              <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
                <Users className="w-8 h-8 text-indigo-500" />
                Face Data Management
              </h1>
            </div>
            <p className="text-neutral-400 mt-1 ml-10">Register, edit, and manage face profiles</p>
          </div>
          <button
            onClick={openAdd}
            className="mt-4 md:mt-0 flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-sm font-semibold transition-colors"
          >
            <Plus className="w-4 h-4" />
            Register New Face
          </button>
        </header>

        <div className="rounded-3xl bg-neutral-900 border border-neutral-800 p-6">
          <div className="relative">
            <Search className="absolute left-3 top-3 w-4 h-4 text-neutral-500" />
            <input
              type="text"
              placeholder="Search by name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-xl pl-10 pr-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredUsers.map((user) => (
            <div
              key={user.id}
              className="rounded-3xl bg-neutral-900 border border-neutral-800 p-5 hover:border-neutral-700 transition-colors group relative"
            >
              <div className="flex items-start justify-between mb-4">
                <img
                  src={getPhotoUrl(user.photo)}
                  alt={user.name}
                  className="w-16 h-16 rounded-2xl object-cover border border-neutral-700"
                />
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => openEdit(user)}
                    className="p-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-white transition-colors"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(user.id, user.name)}
                    className="p-2 rounded-lg bg-neutral-800 hover:bg-red-500/20 text-neutral-400 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div>
                <h3 className="font-semibold text-white truncate">{user.name}</h3>
                <p className="text-xs text-neutral-400 truncate mt-0.5">{user.email}</p>
                <div className="flex items-center gap-2 mt-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${
                    user.role === "admin" ? "bg-purple-500/10 text-purple-400" :
                    user.role === "user" ? "bg-indigo-500/10 text-indigo-400" :
                    "bg-neutral-700 text-neutral-300"
                  }`}>{user.role}</span>
                  <span className="text-xs text-neutral-500">
                    {user.created_at ? new Date(user.created_at).toLocaleDateString() : ""}
                  </span>
                </div>
              </div>
            </div>
          ))}
          {filteredUsers.length === 0 && (
            <div className="col-span-full text-center py-16 text-neutral-500">
              {search ? "No users match your search" : "No registered users yet"}
            </div>
          )}
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-3xl p-6 w-full max-w-md shadow-2xl relative">
            <button
              onClick={() => setShowModal(false)}
              className="absolute top-4 right-4 text-neutral-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 className="text-xl font-bold text-white mb-6">
              {editingUser ? "Edit Face Data" : "Register New Face"}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Full Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. John Doe"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. john@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="guest">Guest</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-1">
                  {editingUser ? "New Photo (optional)" : "Face Photo"}
                </label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setForm({ ...form, file: e.target.files ? e.target.files[0] : null })}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl px-4 py-2 text-white file:mr-4 file:py-1 file:px-3 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-500/10 file:text-indigo-400 hover:file:bg-indigo-500/20"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full py-3 mt-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-colors disabled:opacity-50"
              >
                {submitting ? "Saving..." : editingUser ? "Update Profile" : "Register"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
