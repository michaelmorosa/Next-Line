// Imported from index.js so the task exists before the OS delivers background GPS points.
import * as TaskManager from 'expo-task-manager';
import { LOCATION_TASK, handleLocations } from './recorder';

TaskManager.defineTask(LOCATION_TASK, ({ data, error }) => {
  if (error || !data?.locations) return;
  handleLocations(data.locations);
});
