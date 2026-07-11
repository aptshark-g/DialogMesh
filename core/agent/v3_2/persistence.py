import os, json, time, asyncio
from pathlib import Path
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from .integration import V32Pipeline

class PersistenceManager:
    SAVE_INTERVAL = 60
    MAX_BACKUPS = 50

    def __init__(self, pipeline, save_dir="v32_data"):
        self.pipe = pipeline
        self.save_dir = Path(save_dir)
        self.graph_dir = self.save_dir / "graphs"
        self.session_dir = self.save_dir / "sessions"
        self.profile_path = self.save_dir / "profile.json"
        self.blocktree_path = self.save_dir / "block_tree.json"
        for d in [self.save_dir, self.graph_dir, self.session_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self._task = None
        self._running = False

    async def save_graph(self, version=None):
        if not self.pipe.enable_graph or not self.pipe.graph: return
        ver = version or time.strftime("%Y%m%d_%H%M%S")
        path = self.graph_dir / f"graph_{ver}.json"
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.pipe.graph.save(str(path)))
        except Exception as e:
            import logging; logging.warning(f"[Persist] graph save: {e}")

    def _save_profile_sync(self):
        if not hasattr(self.pipe, '_profile_updater') or not self.pipe._profile_updater: return
        with open(str(self.profile_path), 'w', encoding='utf-8') as f:
            json.dump(self.pipe._profile_updater.profile.to_dict(), f, ensure_ascii=False, indent=2)

    async def save_profile(self):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._save_profile_sync)
        except Exception as e:
            import logging; logging.warning(f"[Persist] profile save: {e}")

    def _save_blocktree_sync(self):
        try:
            bt = self.pipe.block_tree
            if not bt: return
            blocks_dict = {}
            for bid in list(bt.blocks.keys())[:500]:
                block = bt.blocks.get(bid)
                if block:
                    blocks_dict[bid] = block.to_dict() if hasattr(block, 'to_dict') else {"id": bid}
            data = {"summary": bt.get_tree_summary(), "blocks": blocks_dict}
            with open(str(self.blocktree_path), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    async def save_all(self, force_graph=False):
        tasks = []
        if force_graph: tasks.append(self.save_graph())
        tasks.append(self.save_profile())
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_blocktree_sync)
        if tasks: await asyncio.gather(*tasks)

    async def auto_save_loop(self):
        self._running = True
        while self._running:
            await asyncio.sleep(self.SAVE_INTERVAL)
            try:
                await self.save_graph(); await self.save_profile()
            except Exception: pass

    def start_auto_save(self):
        if self._task is not None and not self._task.done(): return
        self._task = asyncio.create_task(self.auto_save_loop())

    def stop_auto_save(self):
        self._running = False
        if self._task: self._task.cancel(); self._task = None

    async def restore(self):
        if self.profile_path.exists():
            try:
                from .predictor.cognitive_profile import CognitiveProfile
                data = json.loads(self.profile_path.read_text(encoding='utf-8'))
                profile = CognitiveProfile.from_dict(data)
                if hasattr(self.pipe, '_profile_updater'):
                    self.pipe._profile_updater.profile = profile
                if hasattr(self.pipe, '_profile_matcher'):
                    self.pipe._profile_matcher.profile = profile
                import logging; logging.info(f"[Persist] Profile restored: meta={profile.metacognition:.2f}")
                return True
            except Exception as e:
                import logging; logging.warning(f"[Persist] Profile restore: {e}")
        return False

    def close(self):
        self.stop_auto_save()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.save_all(force_graph=True))
        except Exception: pass

    def get_stats(self):
        graphs = list(self.graph_dir.glob('graph_*.json'))
        sessions = list(self.session_dir.glob('*.jsonl'))
        return {"graph_backups": len(graphs), "sessions": len(sessions),
                "profile_exists": self.profile_path.exists(),
                "auto_save_running": self._running}
