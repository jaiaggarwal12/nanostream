/**
 * NanoStream Video Player
 * React component with adaptive bitrate streaming
 * 
 * Usage:
 * <VideoPlayer manifestUrl="http://localhost:8000/path/to/master.m3u8" />
 */

import React, { useRef, useEffect, useState } from 'react';

// Note: Install video.js with: npm install video.js video.js-hls

const VideoPlayer = ({ manifestUrl, title = 'Video' }) => {
  const videoRef = useRef(null);
  const [player, setPlayer] = useState(null);
  const [stats, setStats] = useState({
    bandwidth: '5 Mbps',
    quality: '720p',
    buffered: 0,
  });

  useEffect(() => {
    if (!videoRef.current) return;

    // Dynamically import video.js (handles HLS automatically)
    const initPlayer = async () => {
      const videojs = (await import('video.js')).default;

      const player = videojs(videoRef.current, {
        controls: true,
        preload: 'auto',
        fluid: true,
        responsiveUI: true,
        sources: [
          {
            src: manifestUrl,
            type: 'application/x-mpegURL', // HLS MIME type
          },
        ],
        html5: {
          hls: {
            // Enable adaptive bitrate
            abr: {
              enabled: true,
            },
          },
        },
        plugins: {
          qualityLevels: {
            default: false,
          },
        },
      });

      // Monitor bitrate and quality changes
      const updateStats = () => {
        if (player.tech_ && player.tech_.hls) {
          const hls = player.tech_.hls;
          const bandwidth = hls.playlists?.currentPlaylist?.attributes?.BANDWIDTH;
          const currentHeight = hls.playlists?.media?.attributes?.RESOLUTION?.height;
          
          if (bandwidth) {
            setStats(prev => ({
              ...prev,
              bandwidth: `${(bandwidth / 1000000).toFixed(1)} Mbps`,
              quality: `${currentHeight}p`,
            }));
          }
        }

        // Update buffer
        const buffered = player.buffered();
        if (buffered.length > 0) {
          const bufferEnd = buffered.end(buffered.length - 1);
          const currentTime = player.currentTime();
          const bufferedSeconds = Math.max(0, bufferEnd - currentTime);
          setStats(prev => ({
            ...prev,
            buffered: Math.round(bufferedSeconds),
          }));
        }
      };

      player.on('play', updateStats);
      player.on('timeupdate', updateStats);
      player.on('loadedmetadata', updateStats);

      setPlayer(player);

      return () => {
        if (player) player.dispose();
      };
    };

    initPlayer();
  }, [manifestUrl]);

  return (
    <div style={{ maxWidth: '100%', margin: '0 auto' }}>
      <h2>{title}</h2>
      
      <video
        ref={videoRef}
        className="video-js vjs-default-skin"
        style={{
          width: '100%',
          height: 'auto',
          marginBottom: '20px',
        }}
      />

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '15px',
        marginTop: '20px',
        padding: '15px',
        backgroundColor: '#f5f5f5',
        borderRadius: '8px',
      }}>
        <div>
          <strong>Bandwidth:</strong>
          <p>{stats.bandwidth}</p>
        </div>
        <div>
          <strong>Quality:</strong>
          <p>{stats.quality}</p>
        </div>
        <div>
          <strong>Buffered:</strong>
          <p>{stats.buffered}s</p>
        </div>
      </div>

      <div style={{
        marginTop: '20px',
        padding: '15px',
        backgroundColor: '#e3f2fd',
        borderRadius: '8px',
        fontSize: '14px',
      }}>
        <strong>ℹ️ Adaptive Bitrate Streaming</strong>
        <p>
          This player automatically adjusts quality based on your network bandwidth.
          The current quality is shown above and changes as your connection varies.
        </p>
        <p>
          Manifest: <code>{manifestUrl}</code>
        </p>
      </div>
    </div>
  );
};

export default VideoPlayer;


/**
 * INSTALLATION & USAGE
 * 
 * 1. Install dependencies:
 *    npm install react video.js
 * 
 * 2. In your HTML, include video.js CSS:
 *    <link href="https://vjs.zencdn.net/7.20.3/video-js.css" rel="stylesheet" />
 * 
 * 3. Use the component:
 *    import VideoPlayer from './VideoPlayer';
 *    
 *    export default function App() {
 *      return (
 *        <VideoPlayer 
 *          manifestUrl="http://localhost:8000/hls_output/master.m3u8"
 *          title="My Video"
 *        />
 *      );
 *    }
 * 
 * 4. video.js will automatically handle HLS with adaptive bitrate.
 *    It detects available bandwidths and quality levels from the master.m3u8
 *    and switches between them transparently.
 */
