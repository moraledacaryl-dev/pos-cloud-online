'use client';

export default function GlobalError({ error, reset }) {
  return (
    <div style={{ padding: 24 }}>
      <h2>Something went wrong</h2>
      <p style={{ marginTop: 8 }}>{error?.message || 'Unknown error'}</p>
      <button style={{ marginTop: 12 }} onClick={() => reset()}>Try again</button>
    </div>
  );
}
