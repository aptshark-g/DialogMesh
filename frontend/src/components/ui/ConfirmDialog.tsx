import { useUIStore } from '@/stores/uiStore';
import { Modal } from './Modal';
import { Button } from './Button';

export function ConfirmDialog() {
  const modal = useUIStore((s) => s.modal);
  const closeModal = useUIStore((s) => s.closeModal);

  const handleConfirm = () => {
    modal.onConfirm?.();
    closeModal();
  };

  const handleCancel = () => {
    modal.onCancel?.();
    closeModal();
  };

  return (
    <Modal
      isOpen={modal.isOpen}
      onClose={handleCancel}
      title={modal.title}
      closeOnOverlay={modal.closeOnOverlay}
      footer={
        <>
          <Button variant="ghost" onClick={handleCancel}>
            {modal.cancelText}
          </Button>
          <Button variant="primary" onClick={handleConfirm}>
            {modal.confirmText}
          </Button>
        </>
      }
    >
      <div className="text-sm text-text-secondary leading-relaxed">
        {modal.content}
      </div>
    </Modal>
  );
}
