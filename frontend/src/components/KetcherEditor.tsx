import { Editor } from 'ketcher-react';
import { StandaloneStructServiceProvider } from 'ketcher-standalone';
import 'ketcher-react/dist/index.css';

const provider = new StandaloneStructServiceProvider() as any;

export default function KetcherEditor({ initial, onReady }: { initial?: string; onReady: (k: any) => void }) {
  return (
    <Editor
      staticResourcesUrl=""
      structServiceProvider={provider}
      errorHandler={(m: string) => console.warn('Ketcher:', m)}
      disableMacromoleculesEditor
      onInit={(k: any) => {
        onReady(k);
        if (initial) k.setMolecule(initial).catch(() => undefined);
      }}
    />
  );
}
