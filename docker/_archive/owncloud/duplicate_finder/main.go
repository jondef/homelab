package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"time"

	"github.com/gorilla/mux"
	"github.com/owncloud/ocis/v2/ocis-pkg/service/grpc"
	"github.com/owncloud/ocis/v2/services/web/pkg/config"
)

// DuplicateFile represents a file with its metadata
type DuplicateFile struct {
	Path     string    `json:"path"`
	Size     int64     `json:"size"`
	Hash     string    `json:"hash"`
	ModTime  time.Time `json:"modTime"`
	SpaceID  string    `json:"spaceId"`
}

// DuplicateGroup represents a group of duplicate files
type DuplicateGroup struct {
	Hash  string          `json:"hash"`
	Size  int64           `json:"size"`
	Count int             `json:"count"`
	Files []DuplicateFile `json:"files"`
}

// ScanResult contains the results of a duplicate scan
type ScanResult struct {
	TotalFiles      int              `json:"totalFiles"`
	DuplicateGroups []DuplicateGroup `json:"duplicateGroups"`
	TotalDuplicates int              `json:"totalDuplicates"`
	SpaceWasted     int64            `json:"spaceWasted"`
	ScanTime        time.Duration    `json:"scanTime"`
}

// DuplicateScanner handles the duplicate file detection logic
type DuplicateScanner struct {
	dataPath string
}

// NewDuplicateScanner creates a new scanner instance
func NewDuplicateScanner(dataPath string) *DuplicateScanner {
	return &DuplicateScanner{
		dataPath: dataPath,
	}
}

// calculateFileHash computes SHA256 hash of a file
func (ds *DuplicateScanner) calculateFileHash(filePath string) (string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}

	return hex.EncodeToString(hash.Sum(nil)), nil
}

// scanDirectory recursively scans a directory for files
func (ds *DuplicateScanner) scanDirectory(rootPath string, spaceID string) ([]DuplicateFile, error) {
	var files []DuplicateFile

	err := filepath.Walk(rootPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			log.Printf("Error accessing %s: %v", path, err)
			return nil // Continue scanning other files
		}

		// Skip directories and hidden files
		if info.IsDir() || filepath.Base(path)[0] == '.' {
			return nil
		}

		// Skip small files (less than 1KB) as they're unlikely to be meaningful duplicates
		if info.Size() < 1024 {
			return nil
		}

		hash, err := ds.calculateFileHash(path)
		if err != nil {
			log.Printf("Error calculating hash for %s: %v", path, err)
			return nil
		}

		file := DuplicateFile{
			Path:    path,
			Size:    info.Size(),
			Hash:    hash,
			ModTime: info.ModTime(),
			SpaceID: spaceID,
		}

		files = append(files, file)
		return nil
	})

	return files, err
}

// findDuplicates groups files by hash to identify duplicates
func (ds *DuplicateScanner) findDuplicates(files []DuplicateFile) []DuplicateGroup {
	hashMap := make(map[string][]DuplicateFile)

	// Group files by hash
	for _, file := range files {
		hashMap[file.Hash] = append(hashMap[file.Hash], file)
	}

	var duplicateGroups []DuplicateGroup

	// Find groups with more than one file (duplicates)
	for hash, fileGroup := range hashMap {
		if len(fileGroup) > 1 {
			// Sort files by modification time (newest first)
			sort.Slice(fileGroup, func(i, j int) bool {
				return fileGroup[i].ModTime.After(fileGroup[j].ModTime)
			})

			group := DuplicateGroup{
				Hash:  hash,
				Size:  fileGroup[0].Size,
				Count: len(fileGroup),
				Files: fileGroup,
			}
			duplicateGroups = append(duplicateGroups, group)
		}
	}

	// Sort groups by potential space savings (size * duplicate count)
	sort.Slice(duplicateGroups, func(i, j int) bool {
		savingsI := duplicateGroups[i].Size * int64(duplicateGroups[i].Count-1)
		savingsJ := duplicateGroups[j].Size * int64(duplicateGroups[j].Count-1)
		return savingsI > savingsJ
	})

	return duplicateGroups
}

// ScanForDuplicates performs a complete scan for duplicate files
func (ds *DuplicateScanner) ScanForDuplicates(spacePaths map[string]string) (*ScanResult, error) {
	startTime := time.Now()
	var allFiles []DuplicateFile

	// Scan all spaces
	for spaceID, path := range spacePaths {
		files, err := ds.scanDirectory(path, spaceID)
		if err != nil {
			log.Printf("Error scanning space %s at %s: %v", spaceID, path, err)
			continue
		}
		allFiles = append(allFiles, files...)
	}

	duplicateGroups := ds.findDuplicates(allFiles)

	// Calculate statistics
	totalDuplicates := 0
	spaceWasted := int64(0)

	for _, group := range duplicateGroups {
		totalDuplicates += group.Count
		// Space wasted = size * (count - 1) since we keep one copy
		spaceWasted += group.Size * int64(group.Count-1)
	}

	result := &ScanResult{
		TotalFiles:      len(allFiles),
		DuplicateGroups: duplicateGroups,
		TotalDuplicates: totalDuplicates,
		SpaceWasted:     spaceWasted,
		ScanTime:        time.Since(startTime),
	}

	return result, nil
}

// HTTP Handlers

// scanHandler handles the scan request
func (ds *DuplicateScanner) scanHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// In a real implementation, you'd get space paths from OCIS API
	// For now, using a sample configuration
	spacePaths := map[string]string{
		"personal": filepath.Join(ds.dataPath, "spaces", "personal"),
		"shared":   filepath.Join(ds.dataPath, "spaces", "shared"),
	}

	result, err := ds.ScanForDuplicates(spacePaths)
	if err != nil {
		http.Error(w, fmt.Sprintf("Scan failed: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

// deleteHandler handles file deletion requests
func (ds *DuplicateScanner) deleteHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var request struct {
		FilePaths []string `json:"filePaths"`
	}

	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	var results []struct {
		Path    string `json:"path"`
		Success bool   `json:"success"`
		Error   string `json:"error,omitempty"`
	}

	for _, filePath := range request.FilePaths {
		result := struct {
			Path    string `json:"path"`
			Success bool   `json:"success"`
			Error   string `json:"error,omitempty"`
		}{
			Path: filePath,
		}

		// Security check: ensure file is within allowed paths
		if !ds.isPathAllowed(filePath) {
			result.Error = "Path not allowed"
			results = append(results, result)
			continue
		}

		if err := os.Remove(filePath); err != nil {
			result.Error = err.Error()
		} else {
			result.Success = true
		}

		results = append(results, result)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"results": results,
	})
}

// isPathAllowed checks if a file path is within allowed directories
func (ds *DuplicateScanner) isPathAllowed(filePath string) bool {
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return false
	}

	allowedPath, err := filepath.Abs(ds.dataPath)
	if err != nil {
		return false
	}

	// Check if the file is within the data directory
	rel, err := filepath.Rel(allowedPath, absPath)
	if err != nil {
		return false
	}

	// Path should not start with ".." (outside of allowed directory)
	return !filepath.IsAbs(rel) && !filepath.HasPrefix(rel, "..")
}

// Extension represents the OCIS extension
type Extension struct {
	scanner *DuplicateScanner
	config  *config.Config
}

// NewExtension creates a new extension instance
func NewExtension(cfg *config.Config) *Extension {
	return &Extension{
		scanner: NewDuplicateScanner(cfg.File.MetadataBackend.DataDir),
		config:  cfg,
	}
}

// Run starts the extension service
func (e *Extension) Run() error {
	router := mux.NewRouter()

	// API routes
	api := router.PathPrefix("/api/v1/duplicates").Subrouter()
	api.HandleFunc("/scan", e.scanner.scanHandler).Methods("POST")
	api.HandleFunc("/delete", e.scanner.deleteHandler).Methods("DELETE")

	// Serve static files for the web interface
	router.PathPrefix("/").Handler(http.FileServer(http.Dir("./web/")))

	log.Printf("Starting duplicate scanner extension on port 8080")
	return http.ListenAndServe(":8080", router)
}

func main() {
	// Load configuration
	cfg := &config.Config{
		File: config.File{
			MetadataBackend: config.MetadataBackend{
				DataDir: "/var/lib/ocis",
			},
		},
	}

	// Override with environment variable if set
	if dataDir := os.Getenv("OCIS_DATA_DIR"); dataDir != "" {
		cfg.File.MetadataBackend.DataDir = dataDir
	}

	extension := NewExtension(cfg)
	if err := extension.Run(); err != nil {
		log.Fatal("Failed to start extension:", err)
	}
}