'use client';

import { useEffect, useMemo, useState } from 'react';
import { createUser, fetchRoles, fetchUsers, request, updateUser } from '../../lib/api';

const blankForm = { id: null, username: '', password: '', full_name: '', role: 'cashier', role_ids: [], is_active: true, staff_identity_id: '' };

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [staffIdentities, setStaffIdentities] = useState([]);
  const [userLinks, setUserLinks] = useState([]);
  const [q, setQ] = useState('');
  const [form, setForm] = useState(blankForm);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function loadAll() {
    try {
      const [userRows, roleRows, identityRows, linkRows] = await Promise.all([
        fetchUsers(), fetchRoles(), request('/integrations/staff/identities'), request('/integrations/staff/user-links'),
      ]);
      setUsers(Array.isArray(userRows) ? userRows : []);
      setRoles(Array.isArray(roleRows) ? roleRows : []);
      setStaffIdentities(Array.isArray(identityRows) ? identityRows : []);
      setUserLinks(Array.isArray(linkRows) ? linkRows : []);
    } catch (e) { setError(e.message || 'Failed to load users.'); }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const filteredUsers = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((row) => {
      const linked = userLinks.find((link) => link.user_id === row.id)?.staff_identity;
      return [row.username, row.full_name, row.role, linked?.employee_code, linked?.display_name, ...(row.roles || []).map((r) => r.name)].some((v) => String(v || '').toLowerCase().includes(needle));
    });
  }, [users, userLinks, q]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      const payload = { ...form, role_ids: (form.role_ids || []).map(Number) };
      if (!payload.password) delete payload.password;
      delete payload.staff_identity_id;
      let saved;
      if (form.id) {
        saved = await updateUser(form.id, payload);
        setNotice('User updated.');
      } else {
        saved = await createUser(payload);
        setNotice('User created.');
      }
      const userId = form.id || saved?.id;
      if (userId) {
        await request(`/integrations/staff/user-links/${userId}`, { method: 'PUT', body: JSON.stringify({ staff_identity_id: form.staff_identity_id ? Number(form.staff_identity_id) : null }) });
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
    const linked = userLinks.find((link) => link.user_id === row.id);
    setForm({ id: row.id, username: row.username, password: '', full_name: row.full_name || '', role: row.role || 'cashier', role_ids: row.role_ids || [], is_active: !!row.is_active, staff_identity_id: linked?.staff_identity_id || '' });
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
            <p className="muted">POS login credentials and permissions stay local. Link each staff account to the canonical Staff/Payroll identity for cross-app accountability.</p>
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
          <label className="field">Staff Identity<select value={form.staff_identity_id} onChange={(e) => setForm((prev) => ({ ...prev, staff_identity_id: e.target.value }))}><option value="">Not linked</option>{staffIdentities.map((identity) => { const taken = identity.linked_user_id && identity.linked_user_id !== form.id; return <option key={identity.id} value={identity.id} disabled={taken}>{identity.employee_code} · {identity.display_name}{identity.department ? ` · ${identity.department}` : ''}{!identity.active ? ' · inactive' : ''}{taken ? ' · linked' : ''}</option>; })}</select></label>
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
          <thead><tr><th>Username</th><th>Name</th><th>Staff Identity</th><th>Primary Role</th><th>Assigned Roles</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {filteredUsers.map((row) => (
              <tr key={row.id}>
                <td>{row.username}</td>
                <td>{row.full_name || '-'}</td>
                <td>{(() => { const linked = userLinks.find((link) => link.user_id === row.id)?.staff_identity; return linked ? <><strong>{linked.employee_code}</strong><div className="small muted">{linked.display_name}</div></> : <span className="muted">Not linked</span>; })()}</td>
                <td>{row.role}</td>
                <td>{(row.roles || []).map((role) => role.name).join(', ') || '-'}</td>
                <td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td>
                <td><div className="row wrap"><button type="button" className="secondary" onClick={() => editUser(row)}>Edit</button><button type="button" className="secondary" onClick={() => archiveUser(row)}>{row.is_active ? 'Archive' : 'Reactivate'}</button></div></td>
              </tr>
            ))}
            {!filteredUsers.length && <tr><td colSpan="7" className="muted">No users found.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
