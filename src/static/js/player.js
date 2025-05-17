document.addEventListener("DOMContentLoaded", function () {
    const trackTitle = document.getElementById("track-title");
    const trackArtist = document.getElementById("track-artist");
    const trackCover = document.getElementById("track-cover");
    const audioPlayer = document.getElementById("audio-player");
    const loopButton = document.getElementById("loop-button");
    const prevButton = document.getElementById("prev-button");
    const nextButton = document.getElementById("next-button");
    let loopIcons;

    let loopState = 0;

    let currentTrackIndex = 0;
    //let currentAlbumId = null;
    let tracks = [];

    function updateLoopIcon() {
        loopIcons.forEach((icon, index) => {
            console.log(icon, index)
            icon.classList.toggle("hidden", index !== loopState);
        });
    }

    function updateLoopState() {
        console.log(loopState);
        loopState = (loopState + 1) % 3;
        updateLoopIcon();
    }

    audioPlayer.addEventListener("ended", () => {
        if (loopState === 2) {
            audioPlayer.currentTime = 0;
            audioPlayer.play();
        } else if (loopState === 1 && currentTrackIndex === tracks.length - 1) {
            currentTrackIndex = 0;
            playTrack(tracks[currentTrackIndex]);
        } else if (currentTrackIndex < tracks.length - 1) {
            currentTrackIndex++;
            playTrack(tracks[currentTrackIndex]);
        }
    });

    loopButton.addEventListener("click", updateLoopState);

    nextButton.addEventListener("click", () => {
        if (currentTrackIndex < tracks.length - 1) {
            currentTrackIndex++;
            playTrack(tracks[currentTrackIndex]);
        }
    });

    prevButton.addEventListener("click", () => {
        if (currentTrackIndex > 0) {
            currentTrackIndex--;
            playTrack(tracks[currentTrackIndex]);
        }
    });

    function playTrack(trackId) {
        fetch(`/api/v1/play/${trackId}`)
            .then(response => response.json())
            .then(data => {
                trackTitle.textContent = data.track_title;
                trackArtist.textContent = data.artist_name;
                trackCover.src = data.cover_image;
                trackCover.classList.remove("hidden");
                audioPlayer.src = data.track_url;
                audioPlayer.play();
            })
            .catch(error => console.error("Error fetching track data:", error));
    }

    document.getElementById("close-player").addEventListener("click", () => {
        audioPlayer.pause();
        musicPlayer.style.display = "none";
    });

    document.querySelectorAll(".track-link").forEach(link => {
        link.addEventListener("click", event => {
            event.preventDefault();
            const trackId = link.dataset.trackId;
            playTrack(trackId);
        });
    });

    const observer = new MutationObserver(() => {
        const svgLoads = loopButton.querySelectorAll("svgload");
        
        if (svgLoads.length === 0) {
            loopIcons = loopButton.querySelectorAll("svg")
            observer.disconnect();
        }
    });

    observer.observe(loopButton, { childList: true, subtree: true });
});
