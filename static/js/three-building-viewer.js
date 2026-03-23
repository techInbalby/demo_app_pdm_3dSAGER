// Three.js Building Viewer - Lightweight viewer for single buildings
class ThreeBuildingViewer {
    constructor(containerId, buildingColor = 0xffeb3b) {
        this.container = document.getElementById(containerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.buildingMesh = null;
        this.buildingColor = buildingColor; // Store color for building material
        this.isInitialized = false;
        this._disposed = false; // flag to stop the RAF loop on dispose
        
        if (!this.container) {
            console.error('Three.js viewer container not found:', containerId);
            return;
        }
        
        this.init();
    }
    
    init() {
        try {
            if (typeof THREE === 'undefined') {
                throw new Error('Three.js library not loaded');
            }
            
            // Scene
            this.scene = new THREE.Scene();
            this.scene.background = new THREE.Color(0xffffff);
            
            // Camera - ensure container has dimensions
            let width = this.container.clientWidth;
            let height = this.container.clientHeight;
            
            // If container has no dimensions, use CSS dimensions or defaults
            if (width === 0 || height === 0) {
                const computedStyle = window.getComputedStyle(this.container);
                width = parseInt(computedStyle.width) || 400;
                height = parseInt(computedStyle.height) || 400;
            }
            
            this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
            this.camera.position.set(0, 0, 150);
            
            // Renderer
            this.renderer = new THREE.WebGLRenderer({ 
                antialias: true,
                alpha: false // Opaque background
            });
            this.renderer.setSize(width, height);
            this.renderer.setPixelRatio(window.devicePixelRatio);
            this.renderer.setClearColor(0xffffff, 1); // White background
            
            // Clear container first
            this.container.innerHTML = '';
            this.container.appendChild(this.renderer.domElement);
            
            // Ensure canvas is visible
            this.renderer.domElement.style.display = 'block';
            this.renderer.domElement.style.width = '100%';
            this.renderer.domElement.style.height = '100%';
            
            // Controls - OrbitControls for interactive camera movement
            // OrbitControls should be loaded from CDN and available as THREE.OrbitControls
            const setupControls = () => {
                try {
                    // OrbitControls from CDN is typically available as THREE.OrbitControls
                    if (typeof THREE !== 'undefined' && THREE.OrbitControls) {
                        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
                        this.controls.enableDamping = true;
                        this.controls.dampingFactor = 0.05;
                        this.controls.minDistance = 10;
                        this.controls.maxDistance = 500;
                        this.controls.enablePan = true;
                        this.controls.enableZoom = true;
                        this.controls.enableRotate = true;
                        this.controls.autoRotate = false;
                        this.controls.screenSpacePanning = false;
                    } else {
                        // Retry if not loaded yet
                        setTimeout(setupControls, 200);
                    }
                } catch (controlsError) {
                    console.warn('OrbitControls setup failed:', controlsError.message);
                }
            };
            
            // Set up controls after a short delay to ensure OrbitControls script is loaded
            setTimeout(setupControls, 100);
            
            // Lighting
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
            this.scene.add(ambientLight);
            
            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(50, 50, 50);
            this.scene.add(directionalLight);
            
            // Grid helper - subtle reference plane
            const gridHelper = new THREE.GridHelper(50, 10, 0xcccccc, 0xeeeeee);
            gridHelper.position.y = -0.1; // Slightly below ground
            this.scene.add(gridHelper);
            
            // Add axes helper (small)
            const axesHelper = new THREE.AxesHelper(10);
            this.scene.add(axesHelper);
            
            // Render once immediately to show white background
            this.renderer.render(this.scene, this.camera);
            
            // Animation loop
            this.animate();
            
            this.isInitialized = true;
        } catch (error) {
            console.error('Error initializing Three.js viewer:', error);
            if (this.container) {
                this.container.innerHTML = `<div style="padding: 20px; text-align: center; color: #dc3545;">Error: ${error.message}</div>`;
            }
        }
    }
    
    animate() {
        if (this._disposed) return; // stop the loop when viewer is disposed
        requestAnimationFrame(() => this.animate());
        
        if (this.controls) {
            this.controls.update();
        }
        
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }
    
    loadBuilding(cityJSON) {
        if (!this.isInitialized) {
            console.error('Three.js viewer not initialized');
            return;
        }
        
        // Clear existing building
        if (this.buildingMesh) {
            this.scene.remove(this.buildingMesh);
            if (this.buildingMesh.geometry) {
                this.buildingMesh.geometry.dispose();
            }
            if (this.buildingMesh.material) {
                this.buildingMesh.material.dispose();
            }
            this.buildingMesh = null;
        }
        
        try {
            const cityObjects = cityJSON.CityObjects || {};
            const vertices = cityJSON.vertices || [];
            const transform = cityJSON.transform || null;
            
            if (Object.keys(cityObjects).length === 0) {
                throw new Error('No city objects in CityJSON');
            }
            
            const objectId = Object.keys(cityObjects)[0];
            const cityObject = cityObjects[objectId];
            const geometries = cityObject.geometry || [];
            
            if (geometries.length === 0) {
                throw new Error('No geometries in city object');
            }
            
            // Process first geometry
            const geometry = geometries[0];

            // Pre-transform vertices once for use by both shape extraction and height calculation
            let transformedVertices = vertices;
            if (transform && vertices.length > 0) {
                transformedVertices = vertices.map(v => [
                    v[0] * transform.scale[0] + transform.translate[0],
                    v[1] * transform.scale[1] + transform.translate[1],
                    v[2] * transform.scale[2] + transform.translate[2]
                ]);
            }

            const buildingShape = this.extractBuildingShape(geometry, transformedVertices);
            
            if (!buildingShape || buildingShape.length < 3) {
                // Fallback: create a simple box building
                const fallbackGeometry = new THREE.BoxGeometry(10, 20, 10);
                const fallbackMaterial = new THREE.MeshStandardMaterial({
                    color: 0xff0000,
                    metalness: 0.1,
                    roughness: 0.8
                });
                this.buildingMesh = new THREE.Mesh(fallbackGeometry, fallbackMaterial);
                this.buildingMesh.position.set(0, 10, 0);
                this.scene.add(this.buildingMesh);
                
                const center = new THREE.Vector3(0, 10, 0);
                const distance = 22;
                const angle = Math.PI / 6;
                this.camera.position.set(
                    distance * Math.cos(angle) * Math.cos(angle),
                    center.y + distance * Math.sin(angle),
                    distance * Math.cos(angle) * Math.sin(angle)
                );
                this.camera.lookAt(center);
                this.camera.updateProjectionMatrix();
                if (this.controls) {
                    this.controls.target.copy(center);
                    this.controls.update();
                }
                this.renderer.render(this.scene, this.camera);
                return;
            }
            
            // Calculate height using pre-transformed vertices
            const height = this.calculateBuildingHeight(geometry, transformedVertices);
            
            // Calculate center and scale
            let centerX = 0, centerY = 0;
            let minX = Infinity, maxX = -Infinity;
            let minY = Infinity, maxY = -Infinity;
            
            buildingShape.forEach(p => {
                centerX += p.x;
                centerY += p.y;
                minX = Math.min(minX, p.x);
                maxX = Math.max(maxX, p.x);
                minY = Math.min(minY, p.y);
                maxY = Math.max(maxY, p.y);
            });
            centerX /= buildingShape.length;
            centerY /= buildingShape.length;
            
            const sizeX = maxX - minX;
            const sizeY = maxY - minY;
            const maxSize = Math.max(sizeX, sizeY);
            
            // Scale coordinates into a viewable range (~50 units)
            let scale = 1;
            if (maxSize > 100) {
                scale = 50 / maxSize;
            } else if (maxSize < 0.1) {
                scale = 50 / maxSize;
            }
            
            // Create 3D shape (centered and scaled)
            const shape = new THREE.Shape();
            const firstPoint = buildingShape[0];
            shape.moveTo((firstPoint.x - centerX) * scale, (firstPoint.y - centerY) * scale);
            
            for (let i = 1; i < buildingShape.length; i++) {
                const point = buildingShape[i];
                shape.lineTo((point.x - centerX) * scale, (point.y - centerY) * scale);
            }
            shape.lineTo((firstPoint.x - centerX) * scale, (firstPoint.y - centerY) * scale);
            
            const scaledHeight = height * scale;
            
            // Extrude
            const extrudeSettings = {
                depth: scaledHeight,
                bevelEnabled: false
            };
            
            const extrudeGeometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
            extrudeGeometry.translate(0, 0, -scaledHeight / 2);
            
            // Material
            const material = new THREE.MeshStandardMaterial({
                color: this.buildingColor,
                metalness: 0.1,
                roughness: 0.8
            });
            
            // Create mesh
            this.buildingMesh = new THREE.Mesh(extrudeGeometry, material);
            this.buildingMesh.visible = true;
            
            // Rotate building to stand upright (Three.js uses Y-up, but we extruded along Z)
            this.buildingMesh.rotation.x = -Math.PI / 2;
            
            this.scene.add(this.buildingMesh);
            
            // Calculate bounding box BEFORE camera fitting
            const boundingBox = new THREE.Box3().setFromObject(this.buildingMesh);
            const boxCenter = boundingBox.getCenter(new THREE.Vector3());
            const boxSize = boundingBox.getSize(new THREE.Vector3());
            
            // Check if building has valid dimensions
            const maxDim = Math.max(boxSize.x, boxSize.y, boxSize.z);
            if (maxDim < 0.001 || !isFinite(maxDim)) {
                throw new Error(`Invalid building dimensions: ${boxSize.x} x ${boxSize.y} x ${boxSize.z}`);
            }
            
            // Fit camera to building
            this.fitCameraToBuilding();
            
            // Verify building is actually visible by checking if it's in camera frustum
            const frustum = new THREE.Frustum();
            frustum.setFromProjectionMatrix(
                new THREE.Matrix4().multiplyMatrices(
                    this.camera.projectionMatrix,
                    this.camera.matrixWorldInverse
                )
            );
            
            if (!frustum.intersectsBox(boundingBox)) {
                // Fix camera position if building is outside frustum
                this.camera.position.set(boxCenter.x, boxCenter.y + maxDim * 1.2, boxCenter.z + maxDim * 1.2);
                this.camera.lookAt(boxCenter);
                this.camera.updateProjectionMatrix();
                if (this.controls) {
                    this.controls.target.copy(boxCenter);
                    this.controls.update();
                }
            }
            
            // The continuous animate() loop handles all subsequent renders
        } catch (error) {
            console.error('Error loading building in Three.js viewer:', error.message);
        }
    }
    
    // Accepts pre-transformed vertices (no transform param needed)
    extractBuildingShape(geometry, transformedVertices) {
        const points = [];
        
        try {
            if (geometry.type === 'Solid' && geometry.boundaries) {
                const outerShell = geometry.boundaries[0];
                if (outerShell && outerShell.length > 0) {
                    const firstFace = outerShell[0];
                    if (firstFace && firstFace.length > 0) {
                        const firstRing = firstFace[0];
                        firstRing.forEach(vertexIdx => {
                            if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                const vertex = transformedVertices[vertexIdx];
                                points.push({ x: vertex[0], y: vertex[1], z: vertex[2] });
                            }
                        });
                    }
                }
            } else if (geometry.type === 'MultiSurface' && geometry.boundaries) {
                if (geometry.boundaries.length > 0) {
                    const firstSurface = geometry.boundaries[0];
                    if (firstSurface && firstSurface.length > 0) {
                        const firstRing = firstSurface[0];
                        firstRing.forEach(vertexIdx => {
                            if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                const vertex = transformedVertices[vertexIdx];
                                points.push({ x: vertex[0], y: vertex[1], z: vertex[2] });
                            }
                        });
                    }
                }
            } else if (geometry.type === 'CompositeSurface' && geometry.boundaries) {
                if (geometry.boundaries.length > 0) {
                    const firstSurface = geometry.boundaries[0];
                    if (firstSurface && firstSurface.length > 0) {
                        const firstRing = firstSurface[0];
                        firstRing.forEach(vertexIdx => {
                            if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                const vertex = transformedVertices[vertexIdx];
                                points.push({ x: vertex[0], y: vertex[1], z: vertex[2] });
                            }
                        });
                    }
                }
            }
            
            // Remove duplicate consecutive points
            const uniquePoints = [];
            for (let i = 0; i < points.length; i++) {
                const prev = uniquePoints[uniquePoints.length - 1];
                const curr = points[i];
                if (!prev || prev.x !== curr.x || prev.y !== curr.y) {
                    uniquePoints.push(curr);
                }
            }
            
            return uniquePoints.length >= 3 ? uniquePoints : points;
        } catch (error) {
            console.error('Error extracting building shape:', error.message);
            return points;
        }
    }
    
    // Accepts pre-transformed vertices (no transform param needed)
    calculateBuildingHeight(geometry, transformedVertices) {
        let minZ = Infinity;
        let maxZ = -Infinity;
        
        try {
            const processVertex = (vertex) => {
                const z = vertex[2];
                minZ = Math.min(minZ, z);
                maxZ = Math.max(maxZ, z);
            };
            
            if (geometry.type === 'Solid' && geometry.boundaries) {
                const outerShell = geometry.boundaries[0];
                if (outerShell) {
                    outerShell.forEach(face => {
                        if (face) {
                            face.forEach(ring => {
                                if (ring) {
                                    ring.forEach(vertexIdx => {
                                        if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                            processVertex(transformedVertices[vertexIdx]);
                                        }
                                    });
                                }
                            });
                        }
                    });
                }
            } else if (geometry.type === 'MultiSurface' && geometry.boundaries) {
                geometry.boundaries.forEach(surface => {
                    if (surface) {
                        surface.forEach(ring => {
                            if (ring) {
                                ring.forEach(vertexIdx => {
                                    if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                        processVertex(transformedVertices[vertexIdx]);
                                    }
                                });
                            }
                        });
                    }
                });
            } else if (geometry.type === 'CompositeSurface' && geometry.boundaries) {
                geometry.boundaries.forEach(surface => {
                    if (surface) {
                        surface.forEach(ring => {
                            if (ring) {
                                ring.forEach(vertexIdx => {
                                    if (vertexIdx >= 0 && vertexIdx < transformedVertices.length) {
                                        processVertex(transformedVertices[vertexIdx]);
                                    }
                                });
                            }
                        });
                    }
                });
            }
            
            return maxZ > minZ ? (maxZ - minZ) : 10;
        } catch (error) {
            console.error('Error calculating building height:', error.message);
            return 10;
        }
    }
    
    fitCameraToBuilding() {
        if (!this.buildingMesh) return;
        
        try {
            const box = new THREE.Box3().setFromObject(this.buildingMesh);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            
            const maxDim = Math.max(size.x, size.y, size.z);
            const distance = Math.max(maxDim * 1.5, 35);
            
            const angle = Math.PI / 6; // 30 degrees — isometric view
            this.camera.position.set(
                center.x + distance * Math.cos(angle) * Math.cos(angle),
                center.y + distance * Math.sin(angle),
                center.z + distance * Math.cos(angle) * Math.sin(angle)
            );
            this.camera.lookAt(center);
            this.camera.updateProjectionMatrix();
            
            if (this.controls) {
                this.controls.target.copy(center);
                this.controls.update();
            }
        } catch (error) {
            console.error('Error fitting camera to building:', error.message);
        }
    }
    
    resize() {
        if (!this.renderer || !this.camera || !this.container) return;
        
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }
    
    dispose() {
        this._disposed = true; // stops the RAF animation loop immediately
        this.isInitialized = false;
        if (this.controls) {
            try { this.controls.dispose(); } catch (_) {}
        }
        if (this.buildingMesh) {
            if (this.scene) this.scene.remove(this.buildingMesh);
            if (this.buildingMesh.geometry) this.buildingMesh.geometry.dispose();
            if (this.buildingMesh.material) this.buildingMesh.material.dispose();
        }
        if (this.renderer) {
            this.renderer.dispose();
            // Force the browser to release the WebGL context immediately
            const gl = this.renderer.getContext();
            if (gl) {
                const ext = gl.getExtension('WEBGL_lose_context');
                if (ext) ext.loseContext();
            }
        }
    }
}
