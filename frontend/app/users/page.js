'use client';

import { useEffect, useMemo, useState } from 'react';
import { createUser, fetchRoles, fetchUsers, updateUser } from '../../lib/api';

const blankForm = { id: null, username: '', password: '', full_name: '', role: 'cashier', role_ids: [], is_active: true };

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [q, setQ] = useState('');
  const [form, setForm] = useState(blankForm);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function loadAll() {
    try {
      const [userRows, roleRows] = await Promise.all([fetchUsers(), fetchRoles()]);
      setUsers(Array.isArray(userRows) ? userRows : []);
      setRoles(Array.isArray(roleRows) ? roleRows : []);
    } catch (e) { setError(e.message || 'Failed to load users.'); }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const filteredUsers = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((row) => [row.username, row.full_name, row.role, ...(row.roles || []).map((r) => r.name)].some((v) => String(v || '').toLowerCase().includes(needle)));
  }, [users, q]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      const payload = { ...form, role_ids: (form.role_ids || []).map(Number) };
      if (!payload.password) delete payload.password;
      if (form.id) {
        await updateUser(form.id, payload);
        setNotice('User updated.');
      } else {
        await createUser(payload);
        setNotice('User created.');
      }
      setForm(blankForm);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to save user.'); }
  }

  function toggleRole(roleId) {
    setForm((prev) => {
      const exists = (prev.role_ids || []).includes(roleId);
      return { ...prev, role_ids: exists ? prev.role_ids.filter((id) => id !== roleId) : [...prev.role_ids, roleId] };
    });
  }

  function editUser(row) {
    setForm({ id: row.id, username: row.username, password: '', full_name: row.full_name || '', role: row.role || 'cashier', role_ids: row.role_ids || [], is_active: !!row.is_active });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function archiveUser(row) {
    setError(''); setNotice('');
    try {
      await updateUser(row.id, { is_active: !row.is_active });
      setNotice(`User ${row.is_active ? 'archived' : 'reactivated'}.`);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to update user status.'); }
  }

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Users</h1>
            <p className="muted">Create, edit, and archive staff accounts while keeping role-based access aligned with the accounting program style.</p>
          </div>
          <input placeholder="Search users" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 220 }} />
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <h2>{form.id ? 'Edit User' : 'Create User'}</h2>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleSubmit}>
          <label className="field">Username<input value={form.username} disabled={!!form.id} onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))} /></label>
          <label className="field">Password<input type="password" placeholder={form.id ? 'Leave blank to keep current password' : ''} value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} /></label>
          <label className="field">Full Name<input value={form.full_name} onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))} /></label>
          <label className="field">Primary Role<select value={form.role} onChange={(e) => setForm((prev) => ({ ...prev, role: e.target.value }))}>{['owner', 'manager', 'cashier', 'kitchen'].map((role) => <option key={role} value={role}>{role}</option>)}</select></label>
          <label className="field">Active<select value={String(!!form.is_active)} onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.value === 'true' }))}><option value="true">Active</option><option value="false">Inactive</option></select></label>
          <div style={{ gridColumn: '1 / -1' }}>
            <div className="small muted" style={{ marginBottom: 8 }}>Assigned roles</div>
            <div className="row wrap">
              {roles.map((row) => (
                <button key={row.id} type="button" className={`stat-chip ${(form.role_ids || []).includes(row.id) ? 'stat-chip-active' : ''}`} onClick={() => toggleRole(row.id)}>{row.name}</button>
              ))}
            </div>
          </div>
          <div className="row wrap"><button className="primary" type="submit">{form.id ? 'Update User' : 'Save User'}</button>{form.id && <button type="button" className="secondary" onClick={() => setForm(blankForm)}>Cancel Edit</button>}</div>
        </form>
      </section>

      <section className="section">
        <h2>Current Users</h2>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Username</th><th>Name</th><th>Primary Role</th><th>Assigned Roles</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {filteredUsers.map((row) => (
              <tr key={row.id}>
                <td>{row.username}</td>
                <td>{row.full_name || '-'}</td>
                <td>{row.role}</td>
                <td>{(row.roles || []).map((role) => role.name).join(', ') || '-'}</td>
                <td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td>
                <td><div className="row wrap"><button type="button" className="secondary" onClick={() => editUser(row)}>Edit</button><button type="button" className="secondary" onClick={() => archiveUser(row)}>{row.is_active ? 'Archive' : 'Reactivate'}</button></div></td>
              </tr>
            ))}
            {!filteredUsers.length && <tr><td colSpan="6" className="muted">No users found.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
