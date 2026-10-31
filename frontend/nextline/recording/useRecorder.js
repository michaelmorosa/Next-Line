import { useEffect, useState } from 'react';
import { getState, subscribe } from './recorder';

export default function useRecorder() {
  const [state, setState] = useState(getState);
  useEffect(() => subscribe(setState), []);
  return state;
}
