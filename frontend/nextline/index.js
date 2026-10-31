import { registerRootComponent } from 'expo';

// Background tasks must be defined when the JS bundle loads, before any component renders, so the OS can wake
// the app and hand it GPS points while the phone is in a pocket.
import './recording/locationTask';
import App from './App';

registerRootComponent(App);
