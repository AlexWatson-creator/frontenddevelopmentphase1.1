interface ConfirmDialogProps {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  confirmClassName?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, body, confirmLabel, confirmClassName, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
        <h2 className="text-base font-semibold text-[#302d27]">{title}</h2>
        <div className="mt-2 text-sm text-stone-500">{body}</div>
        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-[#302d27] transition hover:bg-stone-50">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={confirmClassName ?? "rounded-lg bg-[#ce1b22] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#b01820]"}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
