export type SurveillanceCameraConfig = {
  id: string;
  file_name: string;
  location: string;
  status: string;
  system_mode: "enforcement_mode" | "traffic_management_mode";
  source: string;
  stream_url: string;
  video_url: string;
  address: string;
  location_link: string;
};
