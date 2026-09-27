"use client";

import styles from "./LoadingSpinner.module.css";

type Props = {
  size?: "sm" | "md";
  label?: string;
};

export function LoadingSpinner({ size = "md", label = "読み込み中" }: Props) {
  return (
    <span className={`${styles.wrap} ${styles[size]}`} role="status" aria-live="polite" aria-label={label}>
      <span className={styles.spin} aria-hidden />
    </span>
  );
}
