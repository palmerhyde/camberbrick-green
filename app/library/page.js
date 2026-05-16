import Link from 'next/link'
import { getAllParts } from '../../lib/collection'
import styles from './library.module.css'

export default function LibraryPage() {
  const parts = getAllParts()

  return (
    <div className={styles.shell}>
      <div className={styles.screen}>
        <header className={styles.header}>
          <Link href="/" className={styles.backBtn} aria-label="Home">←</Link>
          <h1 className={styles.headerTitle}>My Library</h1>
        </header>

        <p className={styles.subtitle}>All LEGO parts saved in your collection.</p>

        {parts.length > 0 ? (
          <div className={styles.partList}>
            {parts.map(part => (
              <article key={part.id} className={styles.partCard}>
                <div>
                  <p className={styles.partId}>#{part.id}</p>
                  <p className={styles.partName}>{part.name}</p>
                  {part.category && <p className={styles.partCategory}>{part.category}</p>}
                </div>
                <div className={styles.partMeta}>
                  <p className={styles.partQty}>{part.qty} pcs</p>
                  <p className={styles.partLocation}>{part.location}</p>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>No parts found in your library yet.</div>
        )}
      </div>
    </div>
  )
}
