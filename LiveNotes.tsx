import React, { useState, useEffect, useRef } from 'react';
import { View, ScrollView, Text, Dimensions, TouchableOpacity, Image, Modal, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import Constants from "expo-constants";
import {
    useAudioRecorder,
    AudioModule,
    RecordingPresets,
    setAudioModeAsync,
} from 'expo-audio';
import { useRouter } from 'expo-router';
import ScreenHeader from '../../components/common/screenHeader';
import BottomTabs from '../../components/common/bottomTabs';
import { showToastMessage } from '../../components/common/toastMessage';
import { useTranscriptStorage } from '../../libs/useTranscriptStorage';

const backendUrl = Constants.expoConfig?.extra?.COD_ASR;
const token = Constants.expoConfig?.extra?.JWT_SECRET

interface TranscriptionSegment {
    start: number;
    end: number;
    text: string;
}

interface TranscriptionResponse {
    language: string;
    language_probability: number;
    duration: number;
    process_time: number;
    text: string;
    segments: TranscriptionSegment[];
}

interface TranscriptionResult {
    text: string;
    segments: any[];
    language?: string;
    duration?: number;
}

interface JobResponse {
    job_id: string;
    status: 'queued' | 'pending' | 'processing' | 'completed' | 'failed';
    result?: TranscriptionResult;
    error?: string;
}

function LiveNotes() {
    const router = useRouter()
    const screenWidth = Dimensions.get("window").width;
    const containerWidth = screenWidth * 0.88;
    const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

    const { transcript, setTranscript, handleClearTranscript } = useTranscriptStorage();

    const [images, setImages] = useState<string[]>([]);
    const [transcriptionStatus, setTranscriptionStatus] = useState("");
    const [isEditing, setIsEditing] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [duration, setDuration] = useState(0);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        (async () => {
            const status = await AudioModule.requestRecordingPermissionsAsync();
            if (!status.granted) {
                showToastMessage('error', 'Oops!', 'Permission to access microphone was denied')
            }

            setAudioModeAsync({
                playsInSilentMode: true,
                allowsRecording: true,
            });
        })();
    }, []);

    const pickImage = async () => {
        let result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ['images'],
            allowsMultipleSelection: true,
            quality: 1,
        });

        if (!result.canceled) {
            const newImages = result.assets.map(asset => asset.uri);
            setImages(prev => [...prev, ...newImages]);
        }
    };

    const removeImage = (indexToRemove: number) => {
        setImages(prev => prev.filter((_, index) => index !== indexToRemove));
    };

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, "0")}:${secs
            .toString()
            .padStart(2, "0")}`;
    };

    const startTimer = () => {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = setInterval(() => {
            setDuration(prev => prev + 1);
        }, 1000);
    };

    const stopTimer = () => {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
    };

    const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

    const pollJobStatus = async (jobId: string): Promise<TranscriptionResult> => {
        const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes timeout (CPU inference is slow)
        const POLL_INTERVAL = 2000;
        const startTime = Date.now();

        while (Date.now() - startTime < TIMEOUT_MS) {
            try {
                const res = await fetch(`${backendUrl}/status/${jobId}`, {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json'
                    }
                });

                if (!res.ok) {
                    // If 5xx server error, we might want to retry. 
                    // If 4xx (e.g. 404), it might be fatal.
                    if (res.status >= 500) {
                        console.warn(`Server error ${res.status}, retrying...`);
                        await wait(POLL_INTERVAL);
                        continue;
                    }
                    throw new Error(`Status check failed: ${res.status}`);
                }

                const data: JobResponse = await res.json();

                if (data.status === 'completed' && data.result) {
                    return data.result;
                }

                if (data.status === 'failed') {
                    throw new Error(data.error || 'Transcription failed');
                }

                // If queued, pending, or processing, wait and try again
                await wait(POLL_INTERVAL);

            } catch (error) {
                // Optional: You could implement a max-consecutive-error count here 
                // to avoid aborting on a single network blip.
                console.error("Polling error:", error);
                throw error;
            }
        }

        throw new Error('Transcription timed out after 5 minutes');
    };

    const transcribeAudio = async (
        fileUri: string,
        fileName: string = 'recording.m4a',
        fileType: string = 'audio/m4a' // Changed default to match m4a extension
    ): Promise<void> => {
        setTranscriptionStatus("Uploading...");

        // React Native specific file handling
        const uri = fileUri.startsWith('file://') ? fileUri : `file://${fileUri}`;

        const formData = new FormData();
        formData.append('file', {
            uri: uri,
            name: fileName,
            type: fileType,
        } as any);

        try {
            // 1. Upload and get Job ID
            const apiRes = await fetch(`${backendUrl}/transcribe`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: formData
            });

            if (!apiRes.ok) {
                const errorData = await apiRes.json().catch(() => ({}));
                throw new Error(errorData.detail || `Upload failed with status ${apiRes.status}`);
            }

            const { job_id } = await apiRes.json();

            // 2. Poll for results
            setTranscriptionStatus("Transcribing...");
            const result = await pollJobStatus(job_id);

            if (result.text) {
                setTranscript(prev => prev ? prev + " " + result.text : result.text);
            }

        } catch (error: any) {
            console.error("Transcription error:", error);
            showToastMessage('error', 'Transcription Failed', error.message || 'Could not transcribe audio');
        } finally {
            setTranscriptionStatus("");
        }
    }

    const processUri = async (uri: string) => {
        await transcribeAudio(uri);
    };

    const handleAutoChunking = async () => {
        try {
            stopTimer();
            await audioRecorder.stop();
            const uri = audioRecorder.uri;
            setDuration(0);

            if (uri) {
                processUri(uri);
            }

            await new Promise(resolve => setTimeout(resolve, 1000));
            await audioRecorder.prepareToRecordAsync();
            audioRecorder.record();
            startTimer();
        } catch (err) {
            console.error("Failed to auto chunk recording", err);
        }
    };

    useEffect(() => {
        if (isRecording && duration >= 30) {
            handleAutoChunking();
        }
    }, [duration, isRecording]);

    const handleRecord = async () => {
        try {
            if (isPaused) {
                audioRecorder.record();
                setIsPaused(false);
                setIsRecording(true);
                startTimer();
            } else {
                await audioRecorder.prepareToRecordAsync();
                audioRecorder.record();
                setIsRecording(true);
                setDuration(0);
                startTimer();
            }
        } catch (err) {
            console.error("Failed to start recording", err);
        }
    }

    const handlePause = async () => {
        try {
            audioRecorder.pause();
            setIsPaused(true);
            setIsRecording(false);
            stopTimer();
        } catch (err) {
            console.error("Failed to pause recording", err);
        }
    }

    const handleStop = async () => {
        try {
            await audioRecorder.stop();
            setIsRecording(false);
            setIsPaused(false);
            stopTimer();
            setDuration(0);

            const uri = audioRecorder.uri;
            if (uri) {
                await processUri(uri);
            }
        } catch (err) {
            console.error("Failed to stop recording", err);
        }
    }

    const handleGoToRefineScreen = () => {
        router.push({
            pathname: '/refineNote',
            params: {
                transcript,
                images,
            }
        })
    }

    return (
        <SafeAreaView className="flex-1 bg-background">
            <KeyboardAvoidingView
                className="flex-1"
                behavior={'padding'}
            >
                <View className="flex-1" style={{ width: containerWidth, alignSelf: 'center' }}>
                    <ScreenHeader pageTitle="Live Notes" />

                    <View className="flex-1">
                        <View className='mt-3 px-2 flex flex-row justify-between items-center bg-white h-20 rounded-2xl'>
                            <View className='flex flex-row items-center'>
                                <Ionicons
                                    name="time"
                                    size={20}
                                    color="#64748B"
                                />
                                <Text className='ml-1 text-textSecondary font-semibold'>
                                    {formatTime(duration)}
                                </Text>
                            </View>

                            <View className='flex flex-row items-center'>
                                <TouchableOpacity
                                    onPress={isRecording ? handlePause : handleRecord}
                                    className={`mr-4 w-11 h-11 rounded-full items-center justify-center ${isRecording ? 'bg-red-100' : 'bg-[#1E3A8A]/10'}`}>
                                    <Ionicons
                                        name={isRecording ? "pause" : "mic"}
                                        size={22}
                                        color={isRecording ? "#EF4444" : "#1E3A8A"}
                                    />
                                </TouchableOpacity>

                                {(isRecording || isPaused) && (
                                    <TouchableOpacity
                                        onPress={handleStop}
                                        className="mr-4 w-11 h-11 rounded-full items-center justify-center bg-red-100">
                                        <Ionicons name="stop" size={22} color="#EF4444" />
                                    </TouchableOpacity>
                                )}

                                <TouchableOpacity
                                    onPress={handleGoToRefineScreen}
                                    className="w-11 h-11 rounded-full items-center justify-center bg-[#3B82F6]/10">
                                    <Ionicons name="color-wand" size={22} color="#3B82F6" />
                                </TouchableOpacity>

                                {!isRecording && (
                                    <TouchableOpacity
                                        onPress={pickImage}
                                        className="ml-4 w-11 h-11 rounded-full items-center justify-center bg-[#10B981]/10">
                                        <Ionicons name="image" size={22} color="#10B981" />
                                    </TouchableOpacity>
                                )}
                            </View>
                        </View>

                        {images.length > 0 && (
                            <ScrollView
                                horizontal
                                showsHorizontalScrollIndicator={false}
                                className="mt-4"
                                contentContainerStyle={{ paddingRight: 16 }}
                            >
                                {images.map((uri, index) => (
                                    <View key={index} style={{ marginRight: 12, position: 'relative' }}>
                                        <Image
                                            source={{ uri }}
                                            style={{ width: 96, height: 96 }}
                                            resizeMode="cover"
                                        />
                                        <TouchableOpacity
                                            onPress={() => removeImage(index)}
                                            style={{
                                                position: 'absolute',
                                                top: -1,
                                                right: -1,
                                                width: 22,
                                                height: 22,
                                                borderRadius: 12,
                                                backgroundColor: '#EF4444',
                                                borderWidth: 2,
                                                borderColor: 'white',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                            }}
                                            activeOpacity={0.7}
                                        >
                                            <Ionicons name="close" size={14} color="white" />
                                        </TouchableOpacity>
                                    </View>
                                ))}
                            </ScrollView>
                        )}

                        <View className='mt-5 flex flex-row justify-between items-center'>
                            <Text className='text-base font-semibold text-textPrimary '>
                                Transcript
                            </Text>
                            <View className='flex flex-row items-center gap-2'>
                                {transcript && (
                                    <TouchableOpacity
                                        onPress={handleClearTranscript}
                                        className='bg-red-100 px-3 flex justify-center items-center rounded-lg py-1'>
                                        <Text className='text-sm font-semibold text-red-600'>
                                            Clear
                                        </Text>
                                    </TouchableOpacity>
                                )}
                                <TouchableOpacity
                                    onPress={() => setIsEditing(!isEditing)}
                                    className='bg-[#1E293B]/10 w-14 flex justify-center items-center rounded-lg py-1'>
                                    <Text className='text-base font-semibold text-textPrimary '>
                                        {isEditing ? "Done" : "Edit"}
                                    </Text>
                                </TouchableOpacity>
                            </View>
                        </View>

                        <ScrollView
                            className='bg-white mt-3 p-5 rounded-2xl'
                            contentContainerStyle={{ flexGrow: 1, paddingBottom: 100 }}
                            showsVerticalScrollIndicator={false}
                        >
                            {isEditing ? (
                                <TextInput
                                    className='text-textSecondary text-sm'
                                    multiline
                                    value={transcript}
                                    onChangeText={setTranscript}
                                    style={{ textAlignVertical: 'top', minHeight: 100 }}
                                />
                            ) : (
                                <Text className='text-textSecondary text-sm'>
                                    {transcript || "Live transcription will appear here..."}
                                </Text>
                            )}
                        </ScrollView>
                    </View>
                    <BottomTabs />
                </View>
            </KeyboardAvoidingView>
            <Modal
                transparent={true}
                visible={!!transcriptionStatus}
                animationType="fade"
            >
                <View className="flex-1 justify-center items-center bg-black/50">
                    <View className="bg-white p-4 rounded-2xl items-center w-2/4">
                        <ActivityIndicator size="small" color="#3B82F6" className="mb-4" />
                        <Text className="text-sm font-semibold text-textPrimary text-center">
                            {transcriptionStatus}
                        </Text>
                    </View>
                </View>
            </Modal>
        </SafeAreaView >
    )
}

export default LiveNotes
