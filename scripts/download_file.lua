--[[
  download_file.lua
  Downloads a file from FILE_URL and saves it to DEST_PATH inside the repo.

  Environment variables (set by the workflow):
    FILE_URL   – direct download URL (required)
    DEST_PATH  – destination path inside the repo (optional)
                 Defaults to "uploads/<filename from URL>"
--]]

--- Exit with an error message.
local CHUNK_SIZE = 99 * 1024 * 1024  -- 99 MB in bytes

local function die(msg)
  io.stderr:write("[ERROR] " .. msg .. "\n")
  os.exit(1)
end

local function run(cmd)
  local result = os.execute(cmd)
  -- Lua 5.4 returns true/false; Lua 5.1 returns exit code
  local ok = (result == true) or (result == 0)
  if not ok then
    die("Command failed: " .. cmd)
  end
end

local function capture(cmd)
  local handle = io.popen("bash -c " .. string.format("%q", cmd))
  local out = handle:read("*a")
  handle:close()
  return out:match("^%s*(.-)%s*$")
end

local function filename_from_url(url)
  local name = url:match(".+/([^/?#]+)")
  if not name or name == "" then
    name = "downloaded_file"
  end
  return name
end

local function dirname(path)
  return path:match("^(.*)/[^/]+$")
end

local function sq(s)
  return "'" .. s:gsub("'", "'\\''") .. "'"
end

-- ── Main ─────────────────────────────────────────────────────────────────────

local file_url  = os.getenv("FILE_URL")
local dest_path = os.getenv("DEST_PATH") or ""

if not file_url or file_url == "" then
  die("FILE_URL environment variable is not set.")
end

local base_name = filename_from_url(file_url)
if dest_path == "" then
  dest_path = "uploads/" .. base_name
end

-- Unique branch name: "upload/<filename>-<timestamp>"
local timestamp = capture("date +%Y%m%d%H%M%S")
local branch    = "upload/" .. base_name:gsub("[^%w%-_.]", "_") .. "-" .. timestamp

print("[INFO] Source URL  : " .. file_url)
print("[INFO] Destination : " .. dest_path)
print("[INFO] Branch      : " .. branch)

-- local dir = dirname(dest_path)
-- if dir and dir ~= "" then
--   print("[INFO] Creating directory: " .. dir)
--   -- Write dir into an env var so no quoting issues in the command
--   local env = "DLDIR=" .. "'" .. dir:gsub("'", "'\\''") .. "'"
--   run("env " .. env .. " bash -c 'mkdir -p \"$DLDIR\"'")
-- end

-- Create git branch & switch to it
run("git checkout -b " .. branch)

-- Make parent directory
local dir = dirname(dest_path)
if dir and dir ~= "" then
  print("[INFO] Creating directory: " .. dir)
  run("env DLDIR=" .. sq(dir) .. " bash -c 'mkdir -p \"$DLDIR\"'")
end

-- finally download
local tmp_file = "/tmp/" .. base_name
print("[INFO] Downloading...")
run("env DLURL=" .. sq(file_url) .. " DLOUT=" .. sq(tmp_file)
    .. " bash -c 'curl -L -f --progress-bar -o \"$DLOUT\" \"$DLURL\"'")

-- check file size
local f = io.open(tmp_file, "rb")
if not f then die("Downloaded file not found at: " .. tmp_file) end
local total_size = f:seek("end")
f:close()
if total_size == 0 then die("Downloaded file is empty.") end
print(string.format("[INFO] Downloaded %d bytes (%.2f MB)", total_size, total_size / 1024 / 1024))


-- split file
local num_chunks = math.ceil(total_size / CHUNK_SIZE)
print(string.format("[INFO] Splitting into %d chunk(s) of up to 99 MB...", num_chunks))

local chunk_dir  = dest_path .. ".chunks"
run("env D=" .. sq(chunk_dir) .. " bash -c 'mkdir -p \"$D\"'")

-- write a manifest file listing chunk count and original filename
local manifest_path = chunk_dir .. "/manifest.txt"
local mf = io.open(manifest_path, "w")
if not mf then die("Cannot create manifest file") end
mf:write("filename=" .. base_name .. "\n")
mf:write("chunks=" .. num_chunks .. "\n")
mf:write("total_bytes=" .. total_size .. "\n")
mf:close()

-- write chunks!
local src = io.open(tmp_file, "rb")
if not src then die("Cannot reopen downloaded file for chunking") end

for i = 1, num_chunks do
  local chunk_path = string.format("%s/part_%04d", chunk_dir, i)
  local data = src:read(CHUNK_SIZE)
  if not data then die("Unexpected EOF at chunk " .. i) end
 
  local cf = io.open(chunk_path, "wb")
  if not cf then die("Cannot write chunk: " .. chunk_path) end
  cf:write(data)
  cf:close()
 
  local chunk_size = #data
  print(string.format("[INFO] Chunk %d/%d → %s (%.2f MB)",
    i, num_chunks, chunk_path, chunk_size / 1024 / 1024))
end

src:close()
os.remove(tmp_file)

-- commit and push chunks into the branch
print("[INFO] Committing chunks...")
run("git config user.name  'github-actions[bot]'")
run("git config user.email 'github-actions[bot]@users.noreply.github.com'")
run("git add -A")
run("env MSG=" .. sq("chore: upload " .. base_name .. " (" .. num_chunks .. " chunks) [" .. timestamp .. "]")
    .. " bash -c 'git commit -m \"$MSG\"'")

print("[INFO] Pushing branch: " .. branch)
run("env BRANCH=" .. sq(branch) .. " bash -c 'git push origin \"$BRANCH\"'")
 
print("")
print("[OK] Done! Pushed " .. num_chunks .. " chunk(s) to branch: " .. branch)
print("[OK] Run reassemble.lua with BRANCH=" .. branch .. " to restore the original file.")